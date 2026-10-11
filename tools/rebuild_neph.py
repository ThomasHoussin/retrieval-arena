"""Rebuild Neph BM25 only; mask generation and final review are separate steps.

Run from the repository with .venv/Scripts/python.exe -u tools/rebuild_neph.py.
An interrupted/failed run can use the same command again: completed extractions
are cached. A successfully built index will never be overwritten by this tool.
"""

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
from importlib.metadata import version
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import traceback

from doc_utils import SUPPORTED_EXTENSIONS
from pdf_utils import (
    CACHE_DIR,
    CHUNK_SIZE,
    OVERLAP,
    chunk_document,
    extract_text_by_page,
)

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SOURCE = ROOT / "docs" / "Neph"
DEFAULT_OUTPUT = ROOT / "data" / "bm25_neph_20260928_v2"
SUPPORTED = SUPPORTED_EXTENSIONS | {".pdf"}


def now():
    return datetime.now(timezone.utc).isoformat()


def fingerprint(path: Path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def write_json(path: Path, data):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def configuration(source: Path, output: Path):
    return {
        "pipeline": "neph-bm25-v2",
        "docs_dir": str(source),
        "bm25_index_dir": str(output),
        "cache_dir": str(CACHE_DIR.resolve()),
        "pdf_backend": "marker",
        "stemmer_language": "french",
        "poison": False,
        "chunk_size": CHUNK_SIZE,
        "overlap": OVERLAP,
        # These are the existing bm25_index.py / bm25s defaults, not new tuning.
        "tokenization": {
            "stopwords": "english",
            "lower": True,
            "token_pattern": r"(?u)\b\w\w+\b",
        },
        "source_separators": "/",
        "retry_empty": True,
    }


def check_prerequisites(files):
    extensions = {p.suffix.lower() for p in files}
    if ".epub" in extensions and not shutil.which("pandoc"):
        raise RuntimeError(
            "Pandoc is required for EPUB extraction (not found on PATH)."
        )
    if ".doc" in extensions:
        if sys.platform != "win32":
            raise RuntimeError("DOC extraction requires Microsoft Word on Windows.")
        probe = subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                "if ($null -eq [Type]::GetTypeFromProgID('Word.Application')) { exit 1 }",
            ],
            capture_output=True,
            timeout=30,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if probe.returncode:
            raise RuntimeError("Microsoft Word COM registration is unavailable.")
    if ".pdf" in extensions:
        import torch

        if not torch.cuda.is_available():
            raise RuntimeError(
                "Marker OCR requires the configured CUDA GPU; torch cannot access it."
            )
        print(f"OCR GPU: {torch.cuda.get_device_name(0)}", flush=True)


def prepare_output(source: Path, output: Path):
    if not source.is_dir():
        raise RuntimeError(f"Source directory does not exist: {source}")
    if output == source or output.is_relative_to(source):
        raise RuntimeError("Output must be outside the source corpus.")
    cfg = configuration(source, output)
    config_path = output / "build_config.json"
    if (output / "index_built.json").exists():
        raise RuntimeError(f"Index already built; refusing to overwrite {output}")
    if output.exists() and any(output.iterdir()):
        if (
            not config_path.exists()
            or json.loads(config_path.read_text(encoding="utf-8")) != cfg
        ):
            raise RuntimeError(
                f"Output is not an interrupted run with matching configuration: {output}"
            )
    output.mkdir(parents=True, exist_ok=True)
    write_json(config_path, cfg)
    return cfg


def build_index(chunks, output):
    from bm25_index import build_bm25_index
    import bm25s

    # Only expose root-level index files after save and a successful reload.
    with tempfile.TemporaryDirectory(prefix="building-", dir=output) as staging:
        staged = Path(staging)
        build_bm25_index(
            chunks, {"bm25_index_dir": staged, "stemmer_language": "french"}
        )
        loaded = bm25s.BM25.load(str(staged), load_corpus=True)
        if loaded.scores["num_docs"] != len(chunks) or len(loaded.corpus) != len(
            chunks
        ):
            raise RuntimeError(
                "Reloaded BM25 index has an unexpected number of chunks."
            )
        del loaded
        for artifact in staged.iterdir():
            artifact.replace(output / artifact.name)


def run(source: Path, output: Path, *, preflight=True):
    source, output = source.resolve(), output.resolve()
    cfg = prepare_output(source, output)
    files = sorted(p for p in source.rglob("*") if p.is_file())
    if not any(p.suffix.lower() in SUPPORTED for p in files):
        raise RuntimeError("No supported source documents found.")
    report = {
        "started_at": now(),
        "status": "running",
        "config": cfg,
        "versions": {
            name: version(name)
            for name in ("bm25s", "PyStemmer", "marker-pdf", "PyMuPDF")
        },
        "python": sys.version,
        "discovered_files": len(files),
        "files": [],
    }
    report_path = output / "ingestion_report.json"
    chunks = []
    write_json(report_path, report)
    try:
        if preflight:
            check_prerequisites(files)
        print(f"Source: {source}\nOutput: {output}\nFiles: {len(files)}", flush=True)
        for position, path in enumerate(files, 1):
            relative = path.relative_to(source).as_posix()
            row = {
                "source": relative,
                "extension": path.suffix.lower(),
                "steps": [],
                "status": "processing",
            }
            report["files"].append(row)
            print(f"[{position}/{len(files)}] {relative}", flush=True)
            try:
                row.update(sha256=fingerprint(path), bytes=path.stat().st_size)
                if path.suffix.lower() not in SUPPORTED:
                    row.update(
                        status="ignored",
                        reason="unsupported_format",
                        pages=0,
                        chunks=0,
                        cached=False,
                    )
                else:
                    pages, cached = extract_text_by_page(
                        path,
                        backend="marker",
                        retry_empty=True,
                        diagnostics=row,
                    )
                    if fingerprint(path) != row["sha256"]:
                        raise RuntimeError(
                            "Source changed during extraction; rerun with a stable corpus."
                        )
                    extracted = chunk_document(pages, relative)
                    row.update(
                        status="extracted" if extracted else "empty_pending_review",
                        cached=cached,
                        pages=len(pages),
                        chunks=len(extracted),
                        characters=sum(len(text) for _, text in pages),
                    )
                    chunks.extend(extracted)
                print(
                    f"  {row['status']}: {row['chunks']} chunks; {', '.join(row['steps'])}",
                    flush=True,
                )
            except KeyboardInterrupt:
                row["status"] = "interrupted"
                raise
            except Exception as exc:
                row.update(
                    status="error",
                    error=f"{type(exc).__name__}: {exc}",
                    traceback=traceback.format_exc(),
                )
                stderr = getattr(exc, "stderr", None)
                if stderr:
                    row["extractor_stderr"] = (
                        stderr.decode("utf-8", errors="replace")
                        if isinstance(stderr, bytes)
                        else stderr
                    )
                print(f"  ERROR: {row['error']}", file=sys.stderr, flush=True)
                if stderr:
                    print(row["extractor_stderr"], file=sys.stderr, flush=True)
            finally:
                report["updated_at"] = now()
                write_json(report_path, report)
        report["totals"] = dict(Counter(row["status"] for row in report["files"]))
        report["total_chunks"] = len(chunks)
        if report["totals"].get("error"):
            raise RuntimeError(
                "Extraction errors remain; BM25 was not built. See ingestion_report.json."
            )
        current = sorted(p for p in source.rglob("*") if p.is_file())
        if current != files or any(
            fingerprint(p) != row["sha256"] for p, row in zip(files, report["files"])
        ):
            raise RuntimeError(
                "Source inventory changed during ingestion; rerun with a stable corpus."
            )
        if not chunks:
            raise RuntimeError("No text chunks extracted; BM25 was not built.")
        report["status"] = "building_index"
        write_json(report_path, report)
        build_index(chunks, output)
        report.update(status="index_built_pending_review", finished_at=now())
        write_json(report_path, report)
        write_json(
            output / "index_built.json",
            {
                "status": report["status"],
                "finished_at": report["finished_at"],
                "chunks": len(chunks),
                "empty_documents": report["totals"].get("empty_pending_review", 0),
                "next_step": "User review, then PJ mask and final verification in a separate step.",
            },
        )
        print(f"\nBM25 built: {len(chunks)} chunks. Report: {report_path}", flush=True)
        print("Mask not generated. Final corpus review is still pending.", flush=True)
        return report
    except BaseException as exc:
        report.update(
            status="interrupted" if isinstance(exc, KeyboardInterrupt) else "failed",
            stopped_at=now(),
            failure=f"{type(exc).__name__}: {exc}",
        )
        write_json(report_path, report)
        raise


def main():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    try:
        run(args.source, args.output)
    except KeyboardInterrupt:
        print(
            "Interrupted. Completed extractions remain cached; rerun the same command.",
            file=sys.stderr,
        )
        return 130
    except Exception as exc:
        print(f"FAILED: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

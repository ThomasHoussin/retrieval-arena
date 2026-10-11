# /// script
# requires-python = ">=3.12,<3.15"
# dependencies = ["marker-pdf==2.0.0", "torch>=2.7", "pymupdf4llm"]
# [tool.uv.sources]
# torch = { index = "pytorch-cu128" }
# [[tool.uv.index]]
# name = "pytorch-cu128"
# url = "https://download.pytorch.org/whl/cu128"
# explicit = true
# ///
"""Re-extract specific PDFs with Marker 2 and replace their "marker" cache entries.

Runs in its own uv environment so the project venv keeps Marker 1 / Surya 0.17,
which the fallback chain in pdf_utils depends on. Requires Docker Desktop and an
NVIDIA GPU: Surya 2 serves its OCR model from a vLLM container (several minutes
of warmup on first call).

Usage:
    uv run --no-project tools/marker2_reextract.py <pdf> [<pdf> ...]
    uv run --no-project tools/marker2_reextract.py --pages 0-3 --dry-run <pdf>

The previous cache entry is copied to tmp/marker1-cache-backup/ before being
replaced. Then rebuild BM25 (e.g. rebuild_neph.py --output <new dir>): every
other document is served from the cache.
"""

import argparse
import hashlib
import importlib.metadata
import json
import os
import re
import shutil
import sys
import time
from pathlib import Path

os.environ.setdefault("TORCH_DEVICE", "cuda")
sys.path.insert(0, str(Path(__file__).resolve().parent))

from pdf_utils import _block_to_text, _cache_file, clean_text  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
BACKUP_DIR = ROOT / "tmp" / "marker1-cache-backup"
CONFIG = {"output_format": "json", "force_ocr": True, "disable_image_extraction": True}


def page_number(block, index: int, first_page: int) -> int:
    """Physical 1-based page number, from the block id ("/page/12/Page/0") when present."""
    match = re.match(r"/page/(\d+)/", getattr(block, "id", "") or "")
    return int(match.group(1)) + 1 if match else first_page + index + 1


def main():
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdfs", nargs="+", type=Path)
    parser.add_argument("--pages", help="Marker page_range (0-based), for smoke tests")
    parser.add_argument(
        "--dry-run", action="store_true", help="print pages, keep the cache"
    )
    args = parser.parse_args()
    if args.pages and not args.dry_run:
        parser.error(
            "--pages requires --dry-run: a partial extraction must not replace the cache"
        )

    from marker.config.parser import ConfigParser
    from marker.converters.pdf import PdfConverter
    from marker.models import create_model_dict

    config_dict = CONFIG | ({"page_range": args.pages} if args.pages else {})
    config = ConfigParser(config_dict)
    converter = PdfConverter(
        config=config.generate_config_dict(),
        artifact_dict=create_model_dict(),
        processor_list=config.get_processors(),
        renderer=config.get_renderer(),
    )
    engine = {
        "marker-pdf": importlib.metadata.version("marker-pdf"),
        "surya-ocr": importlib.metadata.version("surya-ocr"),
        "config": CONFIG,
    }
    first_page = int(args.pages.split("-")[0].split(",")[0]) if args.pages else 0

    for pdf in args.pdfs:
        pdf = pdf.resolve()
        sha1 = hashlib.sha1(pdf.read_bytes()).hexdigest()
        print(f"{pdf.name} ({sha1})", flush=True)
        start = time.perf_counter()
        rendered = converter(str(pdf))
        pages = []
        for i, block in enumerate(rendered.children):
            text = clean_text(_block_to_text(block))
            if text:
                pages.append((page_number(block, i, first_page), text))
        seconds = time.perf_counter() - start
        words = sum(len(t.split()) for _, t in pages)
        print(
            f"  {len(rendered.children)} pages, {len(pages)} with text, {words} words, {seconds:.0f}s",
            flush=True,
        )
        if args.dry_run:
            for number, text in pages:
                print(
                    f"--- page {number} ({len(text.split())} words)\n{text[:600]}",
                    flush=True,
                )
            continue
        if not pages:
            print(
                "  ERROR: no text extracted; cache left unchanged",
                file=sys.stderr,
                flush=True,
            )
            continue
        target = _cache_file(sha1, "marker")
        if target.exists():
            BACKUP_DIR.mkdir(parents=True, exist_ok=True)
            shutil.copy2(target, BACKUP_DIR / target.name)
        temporary = target.with_suffix(".json.tmp")
        temporary.write_text(
            json.dumps({"pages": pages, "engine": engine}, ensure_ascii=False),
            encoding="utf-8",
        )
        temporary.replace(target)
        print(f"  cache replaced: {target.name}", flush=True)


if __name__ == "__main__":
    main()

"""Incremental indexer: add/update specific documents without full re-index.

Qdrant: truly incremental (delete old + upsert new chunks for each file).
BM25: full rebuild from cache (extraction is instant, only BM25 scoring is recomputed).

Usage:
    PYTHONIOENCODING=utf-8 uv run python tools/index_add.py <file1> [file2] [...]
    PYTHONIOENCODING=utf-8 uv run python tools/index_add.py --qdrant-only <file1> [...]
    PYTHONIOENCODING=utf-8 uv run python tools/index_add.py --bm25-only
"""

import sys
from pathlib import Path

# Fix Windows encoding
if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

from config import load_config
from doc_utils import SUPPORTED_EXTENSIONS
from pdf_utils import chunk_document, extract_corpus, extract_text_by_page

ALL_EXTENSIONS = {".pdf"} | SUPPORTED_EXTENSIONS


def main():
    cfg = load_config()
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    flags = {a for a in sys.argv[1:] if a.startswith("--")}

    qdrant_only = "--qdrant-only" in flags
    bm25_only = "--bm25-only" in flags

    if qdrant_only and bm25_only:
        print(
            "ERROR: --qdrant-only and --bm25-only are mutually exclusive.",
            file=sys.stderr,
        )
        sys.exit(1)

    if not bm25_only and not args:
        print(
            "Usage: index_add.py [--qdrant-only | --bm25-only] <file1> [file2] ...",
            file=sys.stderr,
        )
        sys.exit(1)

    docs_dir: Path = cfg["docs_dir"]

    # --- Qdrant incremental ---
    if not bm25_only:
        # Deduplicate files
        seen = set()
        files = []
        for arg in args:
            p = Path(arg).resolve()
            if p in seen:
                continue
            seen.add(p)
            # Verify file is inside docs_dir
            try:
                rel = p.relative_to(docs_dir)
            except ValueError:
                print(
                    f"ERROR: {p} is not inside docs_dir ({docs_dir})", file=sys.stderr
                )
                sys.exit(1)
            if not p.is_file():
                print(f"ERROR: {p} does not exist or is not a file.", file=sys.stderr)
                sys.exit(1)
            if p.suffix.lower() not in ALL_EXTENSIONS:
                print(
                    f"ERROR: unsupported file type '{p.suffix}' for {p}",
                    file=sys.stderr,
                )
                sys.exit(1)
            # source must match the relative path used during full indexing
            files.append((p, str(rel)))

        print(f"Processing {len(files)} file(s) for Qdrant...")

        from qdrant_index import upsert_chunks

        model = None
        client = None
        for file_path, source in files:
            print(f"\n--- {source} ---")
            pages, was_cached = extract_text_by_page(
                file_path, backend=cfg["pdf_backend"]
            )
            label = "(cached)" if was_cached else ""
            print(f"  Extracted {len(pages)} pages {label}")

            chunks = chunk_document(pages, source)
            if not chunks:
                print("  WARNING: no chunks produced, skipping.")
                continue
            print(f"  {len(chunks)} chunks")

            model, client = upsert_chunks(chunks, cfg, model=model, client=client)

        print("\nQdrant incremental indexing complete.")

    # --- BM25 full rebuild ---
    if not qdrant_only:
        print("\nRebuilding BM25 index from full corpus (cached extraction)...")
        from bm25_index import build_bm25_index

        all_chunks = extract_corpus(docs_dir, backend=cfg["pdf_backend"])

        if cfg.get("poison", False):
            from corpus_poison import apply_poison, log_poison_stats

            all_chunks, poison_stats = apply_poison(all_chunks)
            log_poison_stats(poison_stats)

        build_bm25_index(all_chunks, cfg)

    print("\nDone.")


if __name__ == "__main__":
    main()

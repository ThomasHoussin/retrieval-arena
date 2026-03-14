"""Unified indexer: extract documents once, build both BM25 and Qdrant indexes."""

import sys

# Fix Windows encoding
if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

from config import load_config
from pdf_utils import extract_corpus


def main():
    cfg = load_config()
    reset = "--reset" in sys.argv

    # 1. Extract all PDFs → chunks (single pass)
    chunks = extract_corpus(cfg["docs_dir"], backend=cfg["pdf_backend"])

    # 2. Apply corpus poison (if enabled)
    if cfg.get("poison", False):
        from corpus_poison import apply_poison, log_poison_stats

        chunks, poison_stats = apply_poison(chunks)
        log_poison_stats(poison_stats)
    else:
        print('Poison: disabled (set "poison": true in config to enable)')

    # 3. Build BM25 index
    from bm25_index import build_bm25_index

    build_bm25_index(chunks, cfg)

    # 4. Build Qdrant index
    from qdrant_index import build_qdrant_index

    build_qdrant_index(chunks, cfg, reset=reset)

    print("\nAll indexes built successfully.")


if __name__ == "__main__":
    main()

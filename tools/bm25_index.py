"""Index PDF corpus with BM25s."""

import sys
from pathlib import PurePosixPath

# Fix Windows encoding
if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

import bm25s
import Stemmer

from config import load_config
from pdf_utils import extract_corpus


def build_bm25_index(chunks: list[dict], cfg: dict):
    """Build and save a BM25 index from pre-extracted chunks."""
    index_dir = cfg["bm25_index_dir"]

    # Enrich only the search input; keep the saved corpus and displayed text intact.
    texts = [
        PurePosixPath(c["source"].replace("\\", "/")).stem + "\n" + c["text"]
        for c in chunks
    ]
    stemmer = Stemmer.Stemmer(cfg["stemmer_language"])
    print("Tokenizing...")
    corpus_tokens = bm25s.tokenize(texts, stemmer=stemmer)

    print("Indexing BM25...")
    retriever = bm25s.BM25()
    retriever.index(corpus_tokens)

    index_dir.mkdir(parents=True, exist_ok=True)
    print(f"Saving BM25 to {index_dir}")
    retriever.save(str(index_dir), corpus=chunks)
    print("BM25 done.")


def main():
    cfg = load_config()
    chunks = extract_corpus(cfg["docs_dir"], backend=cfg["pdf_backend"])

    if cfg.get("poison", False):
        from corpus_poison import apply_poison, log_poison_stats

        chunks, poison_stats = apply_poison(chunks)
        log_poison_stats(poison_stats)
    else:
        print('Poison: disabled (set "poison": true in config to enable)')

    build_bm25_index(chunks, cfg)


if __name__ == "__main__":
    main()

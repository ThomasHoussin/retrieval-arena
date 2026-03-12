"""Search the BM25-indexed D&D corpus."""

import argparse
from pathlib import Path

import bm25s
import Stemmer

INDEX_DIR = Path(__file__).parent.parent / "data" / "bm25_index"


def main():
    parser = argparse.ArgumentParser(description="BM25 search over D&D corpus")
    parser.add_argument("query", help="Search query")
    parser.add_argument(
        "--top-k", type=int, default=10, help="Number of results (default: 10)"
    )
    args = parser.parse_args()

    retriever = bm25s.BM25.load(str(INDEX_DIR), load_corpus=True)
    stemmer = Stemmer.Stemmer("english")

    query_tokens = bm25s.tokenize(args.query, stemmer=stemmer)
    results, scores = retriever.retrieve(query_tokens, k=args.top_k)

    print(f"Query: {args.query}\n")
    for i in range(results.shape[1]):
        doc = results[0, i]
        score = scores[0, i]
        if score <= 0:
            break

        # doc is a dict with text, source, pages, chunk_id
        if isinstance(doc, dict):
            source = doc.get("source", "?")
            pages = doc.get("pages", [])
            text = doc.get("text", "")
        else:
            source = "?"
            pages = []
            text = str(doc)

        # Truncate text for display
        # preview = text[:200] + "..." if len(text) > 200 else text

        print(f"[{score:.4f}] {source} (p.{','.join(str(p) for p in pages)})")
        print(f"  {text}\n")


if __name__ == "__main__":
    main()

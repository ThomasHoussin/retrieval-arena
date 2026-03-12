"""Index D&D PDF corpus with BM25s."""

import sys
from pathlib import Path

# Fix Windows encoding
if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

import bm25s
import Stemmer

from pdf_utils import extract_text_by_page, chunk_document

DOCS_DIR = Path(__file__).parent.parent / "docs"
INDEX_DIR = Path(__file__).parent.parent / "data" / "bm25_index"


def main():
    pdf_files = sorted(DOCS_DIR.glob("**/*.pdf"))
    if not pdf_files:
        print(f"No PDFs found in {DOCS_DIR}")
        sys.exit(1)

    print(f"Found {len(pdf_files)} PDFs")

    all_chunks = []
    for pdf_path in pdf_files:
        rel = pdf_path.relative_to(DOCS_DIR)
        print(f"  Processing: {rel}")
        try:
            pages = extract_text_by_page(pdf_path)
            chunks = chunk_document(pages, str(rel))
            all_chunks.extend(chunks)
            print(f"    {len(pages)} pages, {len(chunks)} chunks")
        except Exception as e:
            print(f"    ERROR: {e}", file=sys.stderr)

    if not all_chunks:
        print("No chunks extracted, aborting.")
        sys.exit(1)

    print(f"\nTotal: {len(all_chunks)} chunks")

    # Tokenize
    texts = [c["text"] for c in all_chunks]
    stemmer = Stemmer.Stemmer("english")
    print("Tokenizing...")
    corpus_tokens = bm25s.tokenize(texts, stemmer=stemmer)

    # Index
    print("Indexing...")
    retriever = bm25s.BM25()
    retriever.index(corpus_tokens)

    # Save
    INDEX_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Saving to {INDEX_DIR}")
    retriever.save(str(INDEX_DIR), corpus=all_chunks)

    print("Done.")


if __name__ == "__main__":
    main()

"""Shared PDF parsing and chunking utilities."""

import re
from pathlib import Path

import pymupdf4llm

CHUNK_SIZE = 512  # words
OVERLAP = 75  # words


def extract_text_by_page(pdf_path: Path) -> list[tuple[int, str]]:
    """Extract text from each page of a PDF using pymupdf4llm. Returns list of (page_num, text)."""
    pages = []
    page_chunks = pymupdf4llm.to_markdown(str(pdf_path), page_chunks=True)
    for chunk in page_chunks:
        page_num = chunk["metadata"]["page_number"]
        text = chunk["text"].strip()
        # Normalize long dot sequences (e.g. TOC lines) to "..."
        text = re.sub(r"\.{3,}", "...", text)
        if text:
            pages.append((page_num, text))
    return pages


def chunk_document(pages: list[tuple[int, str]], source: str) -> list[dict]:
    """Chunk document text into fixed-size word blocks with overlap."""
    word_pages: list[tuple[str, int]] = []
    for page_num, text in pages:
        words = text.split()
        for w in words:
            word_pages.append((w, page_num))

    if not word_pages:
        return []

    chunks = []
    start = 0
    chunk_id = 0

    while start < len(word_pages):
        end = min(start + CHUNK_SIZE, len(word_pages))
        chunk_words = word_pages[start:end]

        text = " ".join(w for w, _ in chunk_words)
        page_nums = sorted(set(p for _, p in chunk_words))

        chunks.append(
            {
                "text": text,
                "source": source,
                "pages": page_nums,
                "chunk_id": chunk_id,
            }
        )

        chunk_id += 1
        start += CHUNK_SIZE - OVERLAP

        # Avoid tiny trailing chunks
        if len(word_pages) - start < OVERLAP:
            break

    return chunks

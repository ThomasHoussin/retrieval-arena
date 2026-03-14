"""Shared PDF parsing and chunking utilities.

Supports two backends:
- "pymupdf" (default): pymupdf4llm, fast, CPU-only, no OCR for complex layouts
- "marker": Marker/Surya, visual layout detection + OCR, requires GPU (~5GB VRAM)
"""

import re
import sys
from pathlib import Path

import pymupdf4llm

CHUNK_SIZE = 512  # words
OVERLAP = 75  # words

# Lazy-loaded Marker models (heavy, ~5GB VRAM — load once, reuse across PDFs)
_marker_models = None
_marker_converter = None


def clean_text(text: str) -> str:
    """Normalize text before chunking to avoid token-dense artifacts from pymupdf4llm.

    Without this, single "words" (per .split()) can contain 900+ chars of <br>-separated
    HTML or long table separators, producing hundreds of tokens and slowing embedding.
    """
    # <br> tags in markdown tables → newline (so they become separate words)
    text = re.sub(r"<br\s*/?>", "\n", text)
    # Long table separators (---...---) → short separator
    text = re.sub(r"-{4,}", "---", text)
    # URLs → placeholder (keeps context for LLM at retrieval time)
    text = re.sub(r"https?://\S+", "[url deleted]", text)
    # Long dot sequences (TOC lines) → "..."
    text = re.sub(r"\.{3,}", "...", text)
    return text


def _get_marker_converter():
    """Lazy-init Marker models and converter (singleton)."""
    global _marker_models, _marker_converter
    if _marker_converter is not None:
        return _marker_converter

    from marker.config.parser import ConfigParser
    from marker.converters.pdf import PdfConverter
    from marker.models import create_model_dict

    print("Loading Marker models...")
    models = create_model_dict()
    config = ConfigParser({"output_format": "json"})
    converter = PdfConverter(
        config=config.generate_config_dict(),
        artifact_dict=models,
        processor_list=config.get_processors(),
        renderer=config.get_renderer(),
    )
    # Assign both only after full success
    _marker_models = models
    _marker_converter = converter
    return _marker_converter


def _block_to_text(block) -> str:
    """Recursively extract text from a Marker JSON block."""
    parts = []
    html = getattr(block, "html", None)
    if html:
        text = re.sub(r"<[^>]+>", "", str(html)).strip()
        if text and "<content-ref" not in text:
            parts.append(text)
    for child in getattr(block, "children", None) or []:
        child_text = _block_to_text(child)
        if child_text:
            parts.append(child_text)
    return "\n".join(parts)


def _extract_pymupdf(pdf_path: Path) -> list[tuple[int, str]]:
    """Extract text using pymupdf4llm (fast, CPU, native PDFs)."""
    pages = []
    page_chunks = pymupdf4llm.to_markdown(str(pdf_path), page_chunks=True)
    for chunk in page_chunks:
        page_num = chunk["metadata"]["page_number"]
        text = clean_text(chunk["text"].strip())
        if text:
            pages.append((page_num, text))
    return pages


def _extract_marker(pdf_path: Path) -> list[tuple[int, str]]:
    """Extract text using Marker/Surya (GPU, OCR, visual layout detection).

    Uses JSON output mode to preserve per-page structure.
    Marker auto-detects whether OCR is needed per page.
    """
    converter = _get_marker_converter()
    rendered = converter(str(pdf_path))

    pages = []
    for i, page_block in enumerate(rendered.children):
        text = _block_to_text(page_block)
        text = clean_text(text)
        if text:
            pages.append((i + 1, text))
    return pages


def extract_text_by_page(
    pdf_path: Path, backend: str = "pymupdf"
) -> list[tuple[int, str]]:
    """Extract text from each page of a PDF. Returns list of (page_num, text).

    Args:
        pdf_path: Path to the PDF file.
        backend: "pymupdf" (fast, CPU) or "marker" (GPU, OCR-capable).
    """
    if backend == "marker":
        return _extract_marker(pdf_path)
    return _extract_pymupdf(pdf_path)


def extract_corpus(docs_dir: Path, backend: str = "pymupdf") -> list[dict]:
    """Extract all PDFs from docs_dir, chunk, and return all chunks.

    This is the shared extraction step used by both indexers.
    """

    pdf_files = sorted(docs_dir.glob("**/*.pdf"))
    if not pdf_files:
        print(f"No PDFs found in {docs_dir}")
        sys.exit(1)

    print(f"Found {len(pdf_files)} PDFs (backend={backend})")

    all_chunks = []
    for pdf_path in pdf_files:
        rel = pdf_path.relative_to(docs_dir)
        print(f"  Processing: {rel}")
        try:
            pages = extract_text_by_page(pdf_path, backend=backend)
            chunks = chunk_document(pages, str(rel))
            all_chunks.extend(chunks)
            print(f"    {len(pages)} pages, {len(chunks)} chunks")
        except Exception as e:
            print(f"    ERROR: {e}", file=sys.stderr)

    if not all_chunks:
        print("No chunks extracted, aborting.")
        sys.exit(1)

    print(f"\nTotal: {len(all_chunks)} chunks")
    return all_chunks


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

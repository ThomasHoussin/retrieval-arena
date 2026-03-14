"""Shared document parsing and chunking utilities.

PDF backends:
- "pymupdf" (default): pymupdf4llm, fast, CPU-only, no OCR for complex layouts
- "marker": Marker/Surya, visual layout detection + OCR, requires GPU (~5GB VRAM)

Non-PDF formats (docx, pptx, rtf, odt, txt, md, htm/html) are handled by doc_utils.
"""

import hashlib
import json
import re
import sys
from pathlib import Path

import pymupdf4llm

CHUNK_SIZE = 512  # words
OVERLAP = 75  # words
CACHE_DIR = Path(__file__).parent.parent / "data" / "pdf_cache"

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
        text = re.sub(r"<[^>]+>", " ", str(html)).strip()
        text = re.sub(r" {2,}", " ", text)
        if text:
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


def _cache_file(sha1: str, backend: str) -> Path:
    """Return cache file path for a given SHA1 + backend."""
    return CACHE_DIR / f"{sha1}_{backend}.json"


def _load_cache(sha1: str, backend: str) -> list[tuple[int, str]] | None:
    """Load cached extraction result, or None on miss/corrupt."""
    path = _cache_file(sha1, backend)
    if not path.exists():
        return None
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return [(p, t) for p, t in data["pages"]]
    except (json.JSONDecodeError, KeyError, ValueError):
        path.unlink(missing_ok=True)
        return None


def _save_cache(sha1: str, backend: str, pages: list[tuple[int, str]]):
    """Save extraction result to cache."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = _cache_file(sha1, backend)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"pages": pages}, f, ensure_ascii=False)


def extract_text_by_page(
    file_path: Path, backend: str = "pymupdf"
) -> tuple[list[tuple[int, str]], bool]:
    """Extract text from a document file. Returns (pages, cached).

    For PDFs, uses the specified backend (pymupdf/marker).
    For other formats (docx, pptx, rtf, odt, txt, md, htm/html),
    delegates to doc_utils and caches as 'direct'.

    Args:
        file_path: Path to the document file.
        backend: PDF backend — "pymupdf" (fast, CPU) or "marker" (GPU, OCR-capable).
                 Ignored for non-PDF formats.

    Returns:
        Tuple of (list of (page_num, text), was_cached).
    """
    # Lazy import to avoid circular dependency (doc_utils imports clean_text from here)
    from doc_utils import SUPPORTED_EXTENSIONS, extract_text

    # SHA1 as content-addressed cache key (not for security)
    sha1 = hashlib.sha1(file_path.read_bytes()).hexdigest()
    ext = file_path.suffix.lower()

    # Determine cache key: PDF uses backend name, others use "direct"
    cache_key = backend if ext == ".pdf" else "direct"

    cached = _load_cache(sha1, cache_key)
    if cached is not None:
        return cached, True

    if ext == ".pdf":
        if backend == "marker":
            pages = _extract_marker(file_path)
        elif backend == "pymupdf":
            pages = _extract_pymupdf(file_path)
        else:
            raise ValueError(
                f"Unknown backend: {backend!r}. Expected 'pymupdf' or 'marker'."
            )
    elif ext in SUPPORTED_EXTENSIONS:
        pages = extract_text(file_path)
    else:
        raise ValueError(f"Unsupported file format: {ext!r}")

    _save_cache(sha1, cache_key, pages)
    return pages, False


def extract_corpus(docs_dir: Path, backend: str = "pymupdf") -> list[dict]:
    """Extract all supported documents from docs_dir, chunk, and return all chunks.

    This is the shared extraction step used by both indexers.
    Supports: PDF, DOCX, PPTX, RTF, ODT, TXT, MD, HTM, HTML.
    """
    from collections import Counter

    # Lazy import to avoid circular dependency (doc_utils imports clean_text from here)
    from doc_utils import SUPPORTED_EXTENSIONS

    all_extensions = {".pdf"} | SUPPORTED_EXTENSIONS
    doc_files = sorted(
        f
        for f in docs_dir.rglob("*")
        if f.suffix.lower() in all_extensions and f.is_file()
    )
    if not doc_files:
        print(f"No supported documents found in {docs_dir}")
        sys.exit(1)

    ext_counts = Counter(f.suffix.lower() for f in doc_files)
    breakdown = ", ".join(f"{count} {ext}" for ext, count in ext_counts.most_common())
    print(f"Found {len(doc_files)} documents ({breakdown})")

    all_chunks = []
    for file_path in doc_files:
        rel = file_path.relative_to(docs_dir)
        try:
            pages, was_cached = extract_text_by_page(file_path, backend=backend)
            label = (
                f"  Processing: {rel} (cached)"
                if was_cached
                else f"  Processing: {rel}"
            )
            print(label)
            chunks = chunk_document(pages, str(rel))
            all_chunks.extend(chunks)
            print(f"    {len(pages)} pages, {len(chunks)} chunks")
        except Exception as e:
            print(f"  ERROR processing {rel}: {e}", file=sys.stderr)

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

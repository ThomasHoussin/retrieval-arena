"""Shared document parsing and chunking utilities.

PDF backends:
- "pymupdf" (default): pymupdf4llm, fast, CPU-only, no OCR for complex layouts
- "marker": Marker/Surya, visual layout detection + OCR, requires GPU (~5GB VRAM)

Non-PDF formats (doc/docx, epub, pptx, rtf, odt, txt, md, htm/html) use doc_utils.
"""

import hashlib
import html
import json
import re
import sys
import tempfile
from pathlib import Path

import pymupdf4llm

CHUNK_SIZE = 512  # words
OVERLAP = 75  # words
CACHE_DIR = Path(__file__).parent.parent / "data" / "pdf_cache"

# Lazy-loaded Marker models (heavy, ~5GB VRAM — load once, reuse across PDFs)
_marker_models = None
_marker_converter = None
_marker_forced_converter = None


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


def _get_marker_converter(force_ocr: bool = False):
    """Lazy-init Marker models and converter (singleton)."""
    global _marker_models, _marker_converter, _marker_forced_converter
    existing = _marker_forced_converter if force_ocr else _marker_converter
    if existing is not None:
        return existing

    from marker.config.parser import ConfigParser
    from marker.converters.pdf import PdfConverter
    from marker.models import create_model_dict

    print("Loading Marker models...")
    models = _marker_models if _marker_models is not None else create_model_dict()
    config = ConfigParser({"output_format": "json", "force_ocr": force_ocr})
    converter = PdfConverter(
        config=config.generate_config_dict(),
        artifact_dict=models,
        processor_list=config.get_processors(),
        renderer=config.get_renderer(),
    )
    # Assign both only after full success
    _marker_models = models
    if force_ocr:
        _marker_forced_converter = converter
    else:
        _marker_converter = converter
    return converter


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


def _extract_marker(
    pdf_path: Path, *, force_ocr: bool = False
) -> list[tuple[int, str]]:
    """Extract text using Marker/Surya (GPU, OCR, visual layout detection).

    Uses JSON output mode to preserve per-page structure.
    Marker auto-detects whether OCR is needed per page.
    """
    converter = (
        _get_marker_converter(force_ocr=True) if force_ocr else _get_marker_converter()
    )
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


def _extract_surya_pdf(pdf_path: Path) -> list[tuple[int, str]]:
    """OCR the full page when Marker classified all its content as a picture."""
    from surya.input.load import load_pdf

    if _marker_models is None:
        _get_marker_converter()
    images, _ = load_pdf(str(pdf_path), dpi=120)
    highres, _ = load_pdf(str(pdf_path), dpi=240)
    predictions = _marker_models["recognition_model"](
        images,
        det_predictor=_marker_models["detection_model"],
        highres_images=highres,
        recognition_batch_size=16,
        detection_batch_size=2,
        math_mode=False,
        sort_lines=True,
    )
    pages = []
    for i, prediction in enumerate(predictions):
        text = "\n".join(line.text for line in prediction.text_lines)
        text = html.unescape(re.sub(r"<[^>]+>", "", clean_text(text))).strip()
        if text:
            pages.append((i + 1, text))
    return pages


def _load_cache(sha1: str, backend: str) -> list[tuple[int, str]] | None:
    """Load cached extraction result, or None on miss/corrupt."""
    path = _cache_file(sha1, backend)
    if not path.exists():
        return None
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        pages = data["pages"]
        if not isinstance(pages, list) or any(
            not isinstance(item, list)
            or len(item) != 2
            or not isinstance(item[0], int)
            or item[0] < 1
            or not isinstance(item[1], str)
            for item in pages
        ):
            return None
        return [(p, t) for p, t in pages]
    except (json.JSONDecodeError, KeyError, ValueError, TypeError):
        return None


def _save_cache(sha1: str, backend: str, pages: list[tuple[int, str]]):
    """Save extraction result to cache."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = _cache_file(sha1, backend)
    # Interrupted extraction must not leave a half-written cache entry.
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=CACHE_DIR, suffix=".tmp", delete=False
    ) as f:
        temp_path = Path(f.name)
        json.dump({"pages": pages}, f, ensure_ascii=False)
    try:
        temp_path.replace(path)
    finally:
        temp_path.unlink(missing_ok=True)


def extract_text_by_page(
    file_path: Path,
    backend: str = "pymupdf",
    *,
    retry_empty: bool = False,
    diagnostics: dict | None = None,
) -> tuple[list[tuple[int, str]], bool]:
    """Extract text from a document file. Returns (pages, cached).

    For PDFs, uses the specified backend (pymupdf/marker).
    For other formats (doc/docx, epub, pptx, rtf, odt, txt, md, htm/html),
    delegates to doc_utils and caches as 'direct'.

    Args:
        file_path: Path to the document file.
        backend: PDF backend — "pymupdf" (fast, CPU) or "marker" (GPU, OCR-capable).
                 Ignored for non-PDF formats.
        retry_empty: Re-extract empty caches and recover empty Marker results
                     using native PDF text, then forced OCR if needed.
        diagnostics: Optional dict populated with cache state and extraction steps.

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

    details = diagnostics if diagnostics is not None else {}
    details.update(sha1=sha1, cache_backend=cache_key, steps=[])
    cached = _load_cache(sha1, cache_key)
    details["cache_state"] = (
        "missing_or_invalid"
        if cached is None
        else "nonempty"
        if any(t.strip() for _, t in cached)
        else "empty"
    )
    if cached is not None and (not retry_empty or any(t.strip() for _, t in cached)):
        details["steps"].append("cache")
        return cached, True

    if ext == ".pdf":
        if backend == "marker":
            details["steps"].append("marker_auto")
            pages = _extract_marker(file_path)
        elif backend == "pymupdf":
            pages = _extract_pymupdf(file_path)
        else:
            raise ValueError(
                f"Unknown backend: {backend!r}. Expected 'pymupdf' or 'marker'."
            )
    elif ext in SUPPORTED_EXTENSIONS:
        details["steps"].append("direct")
        pages = extract_text(file_path)
    else:
        raise ValueError(f"Unsupported file format: {ext!r}")

    if (
        retry_empty
        and ext == ".pdf"
        and backend == "marker"
        and not any(t.strip() for _, t in pages)
    ):
        import pymupdf

        details["steps"].append("native_text_fallback")
        with pymupdf.open(file_path) as document:
            pages = [
                (i + 1, clean_text(page.get_text().strip()))
                for i, page in enumerate(document)
            ]
        pages = [(p, t) for p, t in pages if t.strip()]
        if not pages:
            details["steps"].append("marker_force_ocr")
            pages = _extract_marker(file_path, force_ocr=True)
        if not any(t.strip() for _, t in pages):
            details["steps"].append("surya_direct_ocr")
            pages = _extract_surya_pdf(file_path)
    _save_cache(sha1, cache_key, pages)
    return pages, False


def extract_corpus(docs_dir: Path, backend: str = "pymupdf") -> list[dict]:
    """Extract all supported documents from docs_dir, chunk, and return all chunks.

    This is the shared extraction step used by both indexers.
    Supports: PDF, DOC, DOCX, EPUB, PPTX, RTF, ODT, TXT, MD, HTM, HTML.
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

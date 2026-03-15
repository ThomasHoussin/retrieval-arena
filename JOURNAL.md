# Technical Journal

Decisions, findings, and pitfalls encountered during the project.

---

## 2026-03-14 — Switch embedding model to jina-embeddings-v3

### Why

The initial model (`nomic-ai/nomic-embed-text-v1.5`, 768 dims) is primarily English. Switched to `jinaai/jina-embeddings-v3` (1024 dims, 30+ languages officially, pre-trained on 89) to support multilingual corpora.

### Key findings

- **Task LoRA**: jina-v3 uses task-specific LoRA adapters (`retrieval.query`, `retrieval.passage`). FastEmbed handles them automatically via `query_embed()` / `passage_embed()`. No explicit prefix needed.
- **`mcp-server-qdrant`**: verified in GitHub source code. Uses `passage_embed()` for documents and `query_embed()` for queries → jina-v3 compatible.
- **Vector name**: convention `fast-{model_after_slash}` → `fast-jina-embeddings-v3`. Derived dynamically in `qdrant_index.py` instead of hardcoded.
- **Vector size**: retrieved via `TextEmbedding.list_supported_models()` (public FastEmbed API) instead of hardcoding 1024.
- **fastembed vs fastembed-gpu**: both packages cannot coexist in the same env. `fastembed-gpu` replaces `fastembed` in pyproject.toml. The MCP server (`uvx mcp-server-qdrant`) runs in its own isolated env with CPU `fastembed` — no conflict.
- **License**: CC BY-NC 4.0 (non-commercial). Keep in mind.

---

## 2026-03-14 — Centralized config (`search_bench.json`)

### Why

All paths (corpus, BM25 index, Qdrant collection, model) were hardcoded across 10+ files. Changing the corpus required manual edits in each file.

### Design

- **Single `collection_name` parameter** from which everything is derived:
  - BM25 index: `data/bm25_{collection_name}`
  - Qdrant collection: `{collection_name}`
- **Config resolution chain**: `--config` CLI > `SEARCH_BENCH_CONFIG` env var > auto-discover `search_bench.json` at project root
- **Qdrant wrapper** (`qdrant_mcp_wrapper.py`): needed because `mcp-server-qdrant` is an external package that reads env vars. The wrapper reads the config and sets `QDRANT_URL`, `COLLECTION_NAME`, `EMBEDDING_MODEL` before launching `uvx mcp-server-qdrant`.

---

## 2026-03-14 — Text cleanup before chunking (`clean_text`)

### Problem

Some embedding batches took 253s instead of ~1s. Root cause: pymupdf4llm generates HTML and markdown artifacts that create "words" (per `.split()`) of 900+ characters.

### Identified causes

| Artifact | Example | Max observed size |
|----------|---------|-------------------|
| `<br>` tags in markdown tables | `ft.<br>MOD<br>SAVE<br>**STR**<br>16<br>+3...` | 925 chars |
| Table separators | `---...---` (long dash sequences) | 617 chars |
| D&D Beyond URLs | `https://www.dndbeyond.com/sources/dnd/soee/...` | 77 chars |
| Dot sequences (TOC) | `Chapter 1 .............. 5` | variable |

Word-based chunking (`CHUNK_SIZE = 512` words) massively underestimates the actual token count. A "512-word" chunk can produce 2000+ tokens due to these structures.

### Fix

`clean_text()` function in `pdf_utils.py`, applied before chunking:
1. `<br>` → newline
2. Separators `----...----` → `---`
3. URLs → `[url deleted]` (placeholder so the LLM knows at retrieval time)
4. `...{3,}` → `...`

### Results

| Metric | Before | After |
|--------|--------|-------|
| Max single word len | 925 | 66 |
| Max chars/chunk | 5289 | 4803 |
| Words > 50 chars | ~150+ | 12 |

---

## 2026-03-14 — OCR: Tesseract limitations in pymupdf4llm

### Finding

PyMuPDF embeds Tesseract (no binary needed, just `tessdata/*.traineddata` files). But for scanned multi-column PDFs, the "Full-page OCR" mode bypasses pymupdf4llm's layout engine and reads line by line across columns.

### Tests performed

1. **Standard pymupdf4llm OCR** — columns ignored, text mixed across columns
2. **`import pymupdf.layout` before pymupdf4llm** — same result (Full-page OCR bypasses layout)
3. **2-step: `get_textpage_ocr()` → save PDF → pymupdf4llm** — text layer not persisted in the PDF
4. **2-step with `use_ocr=False`** — page has no extractable text layer

### Conclusion

Tesseract is insufficient for complex layouts (multi-column). Explored alternatives:
- **Marker** (Datalab, Surya-based) — PDF→Markdown pipeline with visual layout detection, ~5GB VRAM, 90+ languages
- **LightOnOCR-2** (1B params) — top olmOCR-Bench score, lightweight
- Larger VLMs (olmOCR 7B, Chandra 9B) — too heavy for 16GB local VRAM

---

## 2026-03-14 — Marker integration as PDF backend

### Why

Tesseract OCR in pymupdf4llm fails on multi-column scanned PDFs (see above). Marker (Datalab, built on Surya) was tested on a scanned multi-column French PDF (Nephilim RPG supplement) and produced excellent results: columns respected, text clean, headings preserved.

### Decision: dual-backend approach

Rather than replacing pymupdf4llm entirely:
- **`pdf_backend: "pymupdf"`** (default) — fast, CPU-only, works great on native PDFs with text layers
- **`pdf_backend: "marker"`** — Marker/Surya with visual layout detection, auto-OCR when needed, requires GPU

This is a global config choice in `search_bench.json`. Both indexers (BM25 + Qdrant) use the same backend via `extract_text_by_page(pdf_path, backend=cfg["pdf_backend"])`.

### Why Marker over alternatives

| Model | Params | VRAM | Layout quality | Approach |
|-------|--------|------|---------------|----------|
| **Marker/Surya** | ~200M | ~5GB | Excellent | Pipeline: layout detection → block-level OCR → rendering |
| LightOnOCR-2 | 1B | ~4GB | Very good | VLM, single-pass, top olmOCR-Bench |
| olmOCR | 7B | ~14GB | Excellent | VLM (Qwen-2-VL), too heavy for 16GB |
| Chandra | 9B | ~18GB | Best open-source | VLM (Qwen-3-VL), too heavy for 16GB |

Marker was chosen for: reasonable VRAM (~5GB), pipeline approach (not a monolithic VLM), 90+ languages, active development, and proven results on our test corpus.

### Technical details

- Marker uses JSON output mode to preserve per-page structure (`rendered.children` = list of page blocks)
- Text extracted recursively from block tree, HTML tags stripped at leaf nodes
- Models are lazy-loaded (singleton) — loaded once at first PDF, reused for subsequent PDFs
- `clean_text()` is applied to Marker output too (same normalization pipeline)
- Marker auto-detects whether a page needs OCR (no `force_ocr` in production code)

### GPU / torch CUDA setup

PyTorch from PyPI is CPU-only. For CUDA, the `pyproject.toml` must point torch to the PyTorch CUDA index:

```toml
[tool.uv.sources]
torch = { index = "pytorch-cu128" }

[[tool.uv.index]]
name = "pytorch-cu128"
url = "https://download.pytorch.org/whl/cu128"
explicit = true
```

`torch` must also be a **direct dependency** (not just transitive via marker-pdf) for the `[tool.uv.sources]` override to take effect.

---

## 2026-03-14 — Multi-format document support

### Why

The Nephilim JDR corpus contains 218 PDFs but also 51 RTFs, 63 HTM/HTML files, 5 TXTs, 4 DOCXs. These were ignored by the indexer.

### Design

- New `tools/doc_utils.py` module with format-specific extractors
- Each extractor returns `list[tuple[int, str]]` (same contract as `_extract_pymupdf`)
- Non-paginated formats return `[(1, full_text)]` — `chunk_document()` handles the rest
- `extract_corpus()` generalized to discover all supported extensions
- `extract_text_by_page()` dispatches by extension: `.pdf` → pymupdf/marker, others → `doc_utils`
- Caching: PDF uses `{sha1}_{backend}.json`, non-PDF uses `{sha1}_direct.json`

### Supported formats

| Format | Library | Notes |
|--------|---------|-------|
| `.pdf` | pymupdf4llm / Marker | Existing, unchanged |
| `.docx` | python-docx | Paragraphs + table cells |
| `.pptx` | python-pptx | Text from all slides |
| `.rtf` | striprtf | Strip RTF control words |
| `.odt` | odfpy | Walk `text:p` elements |
| `.txt`/`.md` | stdlib | UTF-8 with latin-1 fallback |
| `.htm`/`.html` | stdlib html.parser | Custom subclass skips `<script>`/`<style>` |

### Dropped formats

`.doc`, `.ppt`, `.xls` (binary OLE, no good Python lib), `.sxw`, `.kwd` (exotic), `.tex` (PDF output exists). User converts `.doc` files manually via LibreOffice.

### Validation

Extraction warning emitted when `len(text) < 50` for files > 1KB (catches silent parser failures).

---

## 2026-03-15 — Incremental indexing (`index_add.py`)

### Why

Full re-indexing (`index_all.py --reset`) reprocesses the entire corpus: extraction, embedding, and BM25 scoring. For a large corpus (300+ documents), this is slow and wasteful when only a few files changed or were added. Needed a way to add/update specific documents without touching the rest.

### Design

New script `tools/index_add.py` with three modes:

| Mode | Command | What it does |
|------|---------|-------------|
| Default | `index_add.py <file1> [file2]` | Qdrant incremental + BM25 full rebuild |
| Qdrant only | `index_add.py --qdrant-only <file1> [file2]` | Qdrant incremental, skip BM25 |
| BM25 only | `index_add.py --bm25-only` | BM25 full rebuild, no files needed |

### Qdrant: truly incremental

1. Extract text from specified file(s) via `extract_text_by_page()` (uses cache if available)
2. Chunk via `chunk_document()`
3. **Delete** all existing points for that source (`delete_source()` — filter on `metadata.source`)
4. **Upsert** new chunks with fresh embeddings

The embedding model and Qdrant client are initialized once and reused across files to avoid repeated model loading.

### BM25: full rebuild from cache

BM25 (bm25s) doesn't support incremental updates — the scoring model depends on global corpus statistics (IDF). So BM25 is rebuilt from the full corpus, but extraction is instant thanks to the file-level cache in `extract_text_by_page()`. Only BM25 tokenization + scoring is recomputed.

### Payload restructuring in `qdrant_index.py`

To support deletion by source, the Qdrant payload was restructured to nest fields under `metadata`:

```python
# Before (flat)
{"source": "...", "pages": "...", "chunk_id": "..."}

# After (nested)
{"metadata": {"source": "...", "pages": "...", "chunk_id": "..."}}
```

This enables filtering with `FieldCondition(key="metadata.source", match=MatchValue(value=source))`. The nested structure also keeps the payload organized as more fields are added.

**Breaking change**: existing Qdrant collections indexed with the flat payload must be re-indexed (`index_all.py --reset`) for `delete_source()` to work correctly.

### New functions in `qdrant_index.py`

- `delete_source(client, collection_name, source)` — deletes all points matching a source path
- `upsert_chunks(chunks, cfg, model?, client?)` — embed + upsert a batch of chunks, returns `(model, client)` for reuse

### Validation

- Files must be inside `docs_dir` (prevents indexing arbitrary paths)
- File must exist and have a supported extension
- Duplicate file arguments are deduplicated
- Collection must already exist (run `index_all.py` first for initial setup)

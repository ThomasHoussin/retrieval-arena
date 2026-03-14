# Search Bench

Benchmark comparing multiple search strategies over the same document corpus.

## Goal

Evaluate and compare search quality across 7 strategies:

### Constrained agents (fixed strategy)
1. **BM25 simple** — Lexical search, single pass
2. **BM25 2-round** — Round 1: broad expansion. Round 2: targeted gap-filling
3. **Vector DB naive** — Embedding + cosine search via Qdrant (1 pass)
4. **Vector DB 2-round** — Vector search in 2 passes (same logic as BM25 2-round)

### Free agents (LLM chooses strategy)
5. **BM25 free** — BM25 with no round constraints, LLM decides its strategy
6. **Vector free** — Qdrant with no round constraints
7. **Hybrid free** — BM25 + Qdrant combined, no constraints

## Architecture

- **Search agent**: Claude Sonnet, receives a question + a search tool (one per strategy)
- **Corpus**: documents in `docs/` (PDF, DOCX, PPTX, RTF, ODT, TXT, MD, HTM/HTML — configurable via `search_bench.json`)
- **Arbiter**: Claude Opus evaluates the quality of results from each strategy
- Each strategy exposes an MCP tool that the Sonnet agent can call
- Scoring is standardized for objective comparison

## Tech stack

- **Approach**: Each strategy = a standalone script (Python or TS), called by an agent
- **BM25**: `bm25s` + PyStemmer (Python, via `uv`)
- **Vector DB**: Qdrant via Docker (`qdrant/qdrant`)
- **Embeddings**: FastEmbed GPU (`jinaai/jina-embeddings-v3`, 1024 dims, 8192 tokens, multilingual 30+ languages, CC BY-NC 4.0)
- **LLM**: Claude API (Anthropic SDK) — Sonnet for agents, Opus for arbitration
- **Document parsing**: PDF dual-backend (pymupdf4llm / Marker), plus python-docx, python-pptx, striprtf, odfpy for other formats
- **Text cleanup**: `clean_text()` normalizes artifacts before chunking (512 words / 75 overlap)
- **Python**: managed via `uv` (local venv)
- **TS**: `yarn` + `tsx`

## Configuration

File `search_bench.json` at the project root:

```json
{
  "docs_dir": "./docs",
  "collection_name": "my_corpus",
  "stemmer_language": "english",
  "qdrant_url": "http://localhost:6333",
  "embedding_model": "jinaai/jina-embeddings-v3",
  "pdf_backend": "pymupdf",
  "poison": false
}
```

- `docs_dir`: path to document corpus (relative to config file), recurses into subdirectories
- `collection_name`: collection name, used to derive:
  - BM25 index: `data/bm25_{collection_name}`
  - Qdrant collection: `{collection_name}`
- `stemmer_language`: BM25 stemmer language (e.g. `english`, `french`)
- `qdrant_url`: Qdrant server URL
- `embedding_model`: FastEmbed embedding model
- `pdf_backend`: `"pymupdf"` (default, fast, CPU) or `"marker"` (OCR-capable, GPU required)
- `poison`: `false` (default) or `true` — apply corpus poisoning at indexation via `corpus_poison.py`

To switch corpus or collection, edit this file then re-index (both BM25 + Qdrant).

## Ingestion

- `tools/pdf_utils.py`: document parsing orchestrator + PDF backends + chunking
- `tools/doc_utils.py`: non-PDF format extractors (docx, pptx, rtf, odt, txt, md, htm/html)
- **PDF pymupdf backend**: pymupdf4llm → Markdown, fast, CPU-only. Good for native PDFs with text layers.
- **PDF marker backend**: Marker/Surya → JSON block tree → text extraction per page. Visual layout detection + auto-OCR. Requires GPU (~5GB VRAM). Good for scanned PDFs with complex layouts (multi-column, etc.).
- **Non-PDF formats**: python-docx, python-pptx, striprtf, odfpy, stdlib html.parser — all return `[(1, text)]` (single "page")
- `clean_text()` normalizes text before chunking: `<br>` → newline, separators `---`, URLs → `[url deleted]`, `...{3,}` → `...`
- Without this cleanup, some "words" are 900+ chars and slow embedding from 1s to 250s/batch
- See `JOURNAL.md` for technical details and decisions

## Commands

```bash
# Full indexing (extract once, build both BM25 + Qdrant)
PYTHONIOENCODING=utf-8 uv run python tools/index_all.py --reset

# Or individually:
PYTHONIOENCODING=utf-8 uv run python tools/bm25_index.py
PYTHONIOENCODING=utf-8 uv run python tools/qdrant_index.py

# BM25 search
PYTHONIOENCODING=utf-8 uv run python tools/bm25_search.py "query" --top-k 10
```

## Scoring

See `scoring.md` for the full rubric. Summary:

- **Final score = Quality (80%) + Efficiency (20%)**
- **Quality (0–10)**: Accuracy (0–5) + Completeness (0–3) + Faithfulness (0–2), judged by Opus
- **Efficiency (0–10)**: Latency (0–5) + Token usage (0–5), normalized per group
- Benchmark questions in `questions.json` (simple → complex)
- Detailed results in `results/`

## Agents

### Constrained agents

| Agent | Strategy | Engine | Rounds | maxTurns |
|-------|----------|--------|--------|----------|
| `researcher` | BM25 simple | bm25s | 1 | 2 |
| `researcher-2round` | BM25 2-round | bm25s | 2 | 4 |
| `researcher-vector` | Vector naive | Qdrant | 1 | 2 |
| `researcher-vector-2round` | Vector 2-round | Qdrant | 2 | 4 |

### Free agents

| Agent | Engine | maxTurns |
|-------|--------|----------|
| `researcher-bm25-free` | bm25s | default |
| `researcher-vector-free` | Qdrant | default |
| `researcher-hybrid-free` | bm25s + Qdrant | default |

## Conventions

- Package manager: **yarn** (not npm/pnpm)
- Python: always run with `PYTHONIOENCODING=utf-8` (Windows charmap fix)
- Code language: English
- Comments / docs: English
- Use `rtk` for all shell commands (see global instructions)

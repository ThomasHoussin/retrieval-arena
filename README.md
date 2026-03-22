# Search Bench

[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![uv](https://img.shields.io/badge/uv-package%20manager-blueviolet)](https://docs.astral.sh/uv/)
[![Claude Code](https://img.shields.io/badge/Claude%20Code-agents-orange)](https://docs.anthropic.com/en/docs/claude-code)

A benchmark comparing **7 search strategies** over the same document corpus, using [Claude Code](https://docs.anthropic.com/en/docs/claude-code) agents and [MCP](https://modelcontextprotocol.io/) tools.

Each strategy is implemented as a Claude Code sub-agent (Claude Sonnet) with a different search tool. An arbiter (Claude Opus) then evaluates answer quality using a standardized scoring rubric.

The example corpus uses D&D 5th Edition PDFs, but the approach is generic and works with any document collection (PDF, DOCX, PPTX, RTF, ODT, TXT, MD, HTML).

## How it works

```text
  ┌─────────────────────────────────────────────────────────────┐
  │                     INDEXING (one-time)                      │
  │                                                             │
  │  docs/*  ──►  extract + chunk  ──►  BM25 index + Qdrant DB │
  └─────────────────────────────────────────────────────────────┘

                         ┌──────────────┐
                         │ questions.json │
                         └──────┬───────┘
                                │
                    ┌───────────▼───────────┐
                    │  Agent (Claude Sonnet)  │
                    │  1 agent per strategy   │
                    └───────────┬───────────┘
                                │
                 ┌──────────────┼──────────────┐
                 │              │               │
          ┌──────▼──────┐ ┌────▼────┐  ┌───────▼───────┐
          │  BM25 (MCP) │ │  Qdrant │  │  Document      │
          │  bm25s      │ │  (MCP)  │  │  Corpus docs/* │
          └──────┬──────┘ └────┬────┘  └───────────────┘
                 │              │
                 └──────┬───────┘
                        │
               ┌────────▼────────┐
               │  Agent Response  │
               └────────┬────────┘
                        │
               ┌────────▼────────┐
               │  Arbiter (Opus)  │
               │  Quality Score   │
               └─────────────────┘
```

## Search strategies

### Constrained agents (fixed strategy)

| # | Strategy | Engine | Rounds | maxTurns |
|---|----------|--------|--------|----------|
| 1 | **BM25 simple** | bm25s | 1 | 2 |
| 2 | **BM25 2-round** | bm25s | 2 | 4 |
| 3 | **Vector DB naive** | Qdrant | 1 | 2 |
| 4 | **Vector DB 2-round** | Qdrant | 2 | 4 |

### Free agents (LLM chooses strategy)

| # | Strategy | Engine | maxTurns |
|---|----------|--------|----------|
| 5 | **BM25 free** | bm25s | default |
| 6 | **Vector free** | Qdrant | default |
| 7 | **Hybrid free** | bm25s + Qdrant | default |

## Configuration

All tools read from a single config file `search_bench.json` (copy from `search_bench.json.example` and customize):

```json
{
  "docs_dir": "./docs",
  "collection_name": "my_corpus",
  "stemmer_language": "english",
  "qdrant_url": "http://localhost:6333",
  "embedding_model": "jinaai/jina-embeddings-v3",
  "pdf_backend": "marker",
  "poison": false
}
```

| Key | Description |
|-----|-------------|
| `docs_dir` | Path to document corpus (relative to config file), recurses into subdirectories |
| `collection_name` | Used to derive BM25 index dir (`data/bm25_{name}`) and Qdrant collection name |
| `stemmer_language` | BM25 stemmer language (e.g. `english`, `french`) |
| `qdrant_url` | Qdrant server URL |
| `embedding_model` | FastEmbed model for vector embeddings |
| `pdf_backend` | `"pymupdf"` (default, fast, CPU) or `"marker"` (OCR-capable, GPU) |
| `poison` | `false` (default) or `true` — enable [corpus poisoning](#corpus-poisoning-anti-hallucination-detection) |
| `cudnn_path` | `null` (default) — path to cuDNN DLLs directory, Windows only (e.g. `"C:\\Program Files\\NVIDIA\\CUDNN\\v9.20\\bin\\12.9\\x64"`) |

To switch corpus or collection: edit `search_bench.json`, then re-index.

## Ingestion pipeline

### PDF parsing

Two backends are available, selected via `pdf_backend` in `search_bench.json`:

- **`pymupdf`** (default): [pymupdf4llm](https://pymupdf.readthedocs.io/) → Markdown. Fast, CPU-only. Best for native PDFs with text layers.
- **`marker`**: [Marker](https://github.com/datalab-to/marker) (Surya-based) with visual layout detection and auto-OCR. Requires GPU (~5GB VRAM). Best for scanned PDFs with complex layouts (multi-column, tables, sidebars).

Both backends produce per-page text that is then chunked into 512-word blocks with 75-word overlap.

A `clean_text()` function normalizes the text before chunking to avoid token-dense artifacts:
- `<br>` tags (from markdown tables) → newlines
- Long table separators (`----...----`) → `---`
- URLs → `[url deleted]` placeholder
- Long dot sequences (TOC lines) → `...`

This is critical for embedding performance — without it, a single "word" (per `.split()`) could contain 900+ chars of `<br>`-separated HTML, producing hundreds of tokens and slowing embedding from ~1s to 250s per batch.

### Embedding model

**`jinaai/jina-embeddings-v3`** — 570M params, 1024 dims, 8192 token context.

- Multilingual: 30+ languages officially supported, pre-trained on 89
- Task-specific LoRA adapters: `retrieval.query` / `retrieval.passage` (handled automatically by FastEmbed)
- GPU acceleration via `fastembed-gpu` (ONNX Runtime + CUDA)
- License: CC BY-NC 4.0 (non-commercial)

Vector name and dimension are derived dynamically from the model (same convention as `mcp-server-qdrant`).

## Scoring

**Final Score = Quality (80%) + Efficiency (20%)**, range 0-10.

- **Quality (0-10)** — judged by Claude Opus:
  - Accuracy (0-5): factual correctness vs. expected answer
  - Completeness (0-3): all aspects of the question covered
  - Faithfulness (0-2): no hallucination, grounded in search results
- **Efficiency (0-10)** — measured automatically:
  - Latency (0-5): normalized against the group
  - Token usage (0-5): normalized against the group

See [`scoring.md`](scoring.md) for the full rubric.

## Corpus poisoning (anti-hallucination detection)

When `"poison": true` in `search_bench.json`, the indexer applies targeted text mutations to chunks before indexing (BM25 + Qdrant). This creates controlled discrepancies between the indexed corpus and widely-known facts (e.g. Fireball damage `8d6` becomes `6d8`).

**Purpose**: Detect when an agent answers from training memory instead of search results. If an agent returns the original (well-known) value instead of the poisoned value, it's hallucinating. The Faithfulness score (0-2) penalizes this.

**How it works** (`tools/corpus_poison.py`):
- **Global rules**: regex replacements applied to all chunks
- **Contextual rules**: replacements only when a specific keyword is present in the chunk
- Rules are idempotent (match only original values, not replacements)
- Gated by the `poison` config key — `false` by default

## Prerequisites

- **Python 3.12** + [uv](https://docs.astral.sh/uv/)
- **Node.js** + [yarn](https://yarnpkg.com/)
- **Docker** (for Qdrant vector DB)
- **NVIDIA GPU** + CUDA (required for Marker OCR backend and recommended for embedding)
- **Claude Code CLI** with an Anthropic API key

> **Note on the corpus:** This repository does not include document files. You must provide your own documents in the `docs/` directory.

## Setup

### 1. Clone and install dependencies

```bash
git clone https://github.com/<your-username>/search_bench.git
cd search_bench

# Python dependencies (includes fastembed-gpu)
uv sync

# Node dependencies (for TypeScript tooling)
yarn install
```

### 2. Configure

```bash
cp search_bench.json.example search_bench.json
# Edit search_bench.json: set docs_dir, collection_name, stemmer_language, etc.
```

### 3. Add your document corpus

Place your documents in the `docs/` directory (or wherever `docs_dir` points). Supported formats: PDF, DOCX, PPTX, RTF, ODT, TXT, MD, HTML.

### 4. Start Qdrant

```bash
docker run -d --name qdrant -p 6333:6333 \
  -v "$(pwd)/qdrant_storage:/qdrant/storage" \
  qdrant/qdrant
```

### 5. Index

```bash
# Build both indexes in one pass (recommended — extracts documents only once)
PYTHONIOENCODING=utf-8 uv run python tools/index_all.py --reset

# Or build individually:
PYTHONIOENCODING=utf-8 uv run python tools/bm25_index.py
PYTHONIOENCODING=utf-8 uv run python tools/qdrant_index.py
```

Use `--reset` to drop and recreate the Qdrant collection. With Marker backend, always use `index_all.py` to avoid running OCR twice.

To add new documents without re-indexing everything:

```bash
# Add specific documents (Qdrant incremental + BM25 rebuild)
PYTHONIOENCODING=utf-8 uv run python tools/index_add.py docs/my_new_file.pdf

# Rebuild BM25 index only (from cache, no new embedding)
PYTHONIOENCODING=utf-8 uv run python tools/index_add.py --bm25-only
```

## Usage

### Ask a single question

The research agents are available as Claude Code sub-agents. Ask Claude to search your corpus:

> "Search the corpus for combat rules"

Claude will automatically select and use the appropriate researcher agent.

Available agents: `researcher`, `researcher-2round`, `researcher-vector`, `researcher-vector-2round`, `researcher-bm25-free`, `researcher-vector-free`, `researcher-hybrid-free`.

### Standalone CLI search (without Claude Code)

```bash
# BM25 keyword search
PYTHONIOENCODING=utf-8 uv run python tools/bm25_search.py "fireball damage" --top-k 5
```

### Run the benchmark

Ask Claude to run all agents against the questions in `questions.json`. No separate script is needed — Claude orchestrates the agents and collects results into `results/`.

## MCP servers

The agents communicate with search backends via MCP servers. Claude Code launches them automatically from agent configs, but you can run them manually:

### BM25 server

```bash
uv run python tools/bm25_mcp_server.py --config search_bench.json
```

Exposes a `retrieve(query, k)` tool over stdio.

### Qdrant server

```bash
uv run python tools/qdrant_mcp_wrapper.py --config search_bench.json
```

Wraps `mcp-server-qdrant` with config-driven env vars. Exposes a `qdrant-find` tool over stdio.

## Project structure

```text
search_bench/
├── .claude/
│   └── agents/               # Claude Code sub-agent definitions (1 per strategy)
├── data/
│   └── bm25_{collection}/    # Serialized BM25 index (generated)
├── docs/                     # Document corpus (not included — bring your own)
├── results/                  # Benchmark run results (generated)
├── test/                     # Unit tests (pytest)
├── tools/
│   ├── config.py             # Shared config loader (reads search_bench.json)
│   ├── pdf_utils.py          # PDF extraction + clean_text() + chunking
│   ├── doc_utils.py          # Non-PDF format extractors (docx, pptx, rtf, odt, txt, html)
│   ├── index_all.py          # Full index builder (BM25 + Qdrant in one pass)
│   ├── index_add.py          # Incremental indexing (add new documents)
│   ├── bm25_index.py         # Build BM25 index from documents
│   ├── bm25_search.py        # CLI search over BM25 index
│   ├── bm25_mcp_server.py    # BM25 MCP server (config-driven)
│   ├── qdrant_index.py       # Build Qdrant vector index from documents
│   ├── qdrant_mcp_wrapper.py # Wrapper for mcp-server-qdrant (config-driven)
│   ├── extract_page.py       # Extract a single page from a document
│   └── corpus_poison.py      # Anti-hallucination: injects modified stats
├── search_bench.json.example # Config template (copy to search_bench.json)
├── questions.json            # Benchmark questions with expected answers
├── scoring.md                # Full scoring rubric
└── JOURNAL.md                # Technical decisions and findings log
```

## Tech stack

| Component | Technology |
|-----------|------------|
| BM25 search | [`bm25s`](https://github.com/xhluca/bm25s) + PyStemmer |
| Vector search | [Qdrant](https://qdrant.tech/) + [`fastembed-gpu`](https://github.com/qdrant/fastembed) (jina-embeddings-v3, 1024 dims) |
| PDF parsing | [PyMuPDF](https://pymupdf.readthedocs.io/) + pymupdf4llm / [Marker](https://github.com/datalab-to/marker) (Surya OCR) |
| LLM agents | Claude Sonnet (search) / Claude Opus (arbitration) |
| MCP servers | bm25s built-in MCP / [mcp-server-qdrant](https://github.com/qdrant/mcp-server-qdrant) |
| Python | 3.12, managed with [uv](https://docs.astral.sh/uv/) |
| TypeScript | tsx + yarn (tooling) |

## Windows note

On Windows, always prefix Python commands with `PYTHONIOENCODING=utf-8` to avoid encoding errors with PDF text output. On Linux/macOS this is typically not needed.

PowerShell syntax:
```powershell
$env:PYTHONIOENCODING="utf-8"; uv run python tools/qdrant_index.py --reset
```

If you need GPU-accelerated embedding, set `cudnn_path` in `search_bench.json` to point to the directory containing the cuDNN DLLs.

## License

[MIT](LICENSE)

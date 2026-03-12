# Search Bench

[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![uv](https://img.shields.io/badge/uv-package%20manager-blueviolet)](https://docs.astral.sh/uv/)
[![Claude Code](https://img.shields.io/badge/Claude%20Code-agents-orange)](https://docs.anthropic.com/en/docs/claude-code)

A benchmark comparing **5 search strategies** over the same document corpus, using [Claude Code](https://docs.anthropic.com/en/docs/claude-code) agents and [MCP](https://modelcontextprotocol.io/) tools.

Each strategy is implemented as a Claude Code sub-agent (Claude Sonnet) with a different search tool. An arbiter (Claude Opus) then evaluates answer quality using a standardized scoring rubric.

The example corpus uses D&D 5th Edition PDFs, but the approach is generic and works with any PDF collection.

## How it works

```text
                         ┌──────────────┐
                         │  questions.json │
                         └──────┬───────┘
                                │
                    ┌───────────▼───────────┐
                    │   Agent (Claude Sonnet) │
                    │   1 agent per strategy  │
                    └───────────┬───────────┘
                                │
                 ┌──────────────┼──────────────┐
                 │              │               │
          ┌──────▼──────┐ ┌────▼────┐  ┌───────▼───────┐
          │  BM25 (MCP) │ │  Qdrant │  │  PDF Corpus   │
          │  bm25s      │ │  (MCP)  │  │  docs/*.pdf   │
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

| # | Strategy | Engine | Queries | Rounds | Description |
|---|----------|--------|---------|--------|-------------|
| 1 | **BM25 simple** | bm25s | 1 keyword query | 1 | Classical lexical search, single pass |
| 2 | **BM25 + LLM expansion** | bm25s | 2-5 parallel queries | 1 | LLM generates multi-axis keyword queries before searching |
| 3 | **BM25 2-round** | bm25s | 2-5 + 1-3 gap-fill | 2 | Round 1: broad expansion. Round 2: targeted gap-filling |
| 4 | **Vector DB naive** | Qdrant | 1 natural language query | 1 | Cosine similarity search via embeddings |
| 5 | **Vector DB 2-round** | Qdrant | 2-5 + 1-3 gap-fill | 2 | Round 1: multi-axis semantic search. Round 2: gap-filling |

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

## Prerequisites

- **Python 3.12** + [uv](https://docs.astral.sh/uv/) (version pinned in `.python-version`)
- **Node.js** + [yarn](https://yarnpkg.com/)
- **Docker** (for Qdrant vector DB)
- **Claude Code CLI** with an Anthropic API key

> **Note on the corpus:** This repository does not include PDF files. You must provide your own documents in the `docs/` directory. The example questions in `questions.json` reference D&D 5e content (SRD, adventures), but you can adapt them to any corpus.

## Setup

### 1. Clone and install dependencies

```bash
git clone https://github.com/<your-username>/search_bench.git
cd search_bench

# Python dependencies
uv sync

# Node dependencies (for TypeScript tooling)
yarn install
```

### 2. Add your PDF corpus

Place your PDF files in the `docs/` directory:

```text
docs/
├── your-document-1.pdf
├── your-document-2.pdf
└── ...
```

### 3. Build the BM25 index

```bash
PYTHONIOENCODING=utf-8 uv run python tools/bm25_index.py
```

This parses all PDFs in `docs/`, chunks them (512 words, 75-word overlap), and builds a BM25 index in `data/bm25_index/`.

### 4. Start Qdrant and build the vector index

```bash
# Start Qdrant with persistent storage
docker run -d --name qdrant -p 6333:6333 \
  -v "$(pwd)/qdrant_storage:/qdrant/storage" \
  qdrant/qdrant

# Build the vector index
PYTHONIOENCODING=utf-8 uv run python tools/qdrant_index.py
```

This embeds all chunks using `sentence-transformers/all-MiniLM-L6-v2` (via [FastEmbed](https://github.com/qdrant/fastembed), runs locally — no API key needed) and upserts them into a Qdrant collection `dnd5e_chunks`.

Use `--reset` to drop and recreate the collection:

```bash
PYTHONIOENCODING=utf-8 uv run python tools/qdrant_index.py --reset
```

## MCP servers

The agents communicate with the search backends via MCP (Model Context Protocol) servers. Claude Code launches them automatically based on the agent configuration, but you can also run them manually:

### BM25 server (bm25s built-in)

```bash
# Run from the project root
uv run bm25 mcp launch --index-dir data/bm25_index
```

Exposes a `retrieve(query, k)` tool over stdio.

### Qdrant server

```bash
QDRANT_URL=http://localhost:6333 \
COLLECTION_NAME=dnd5e_chunks \
EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2 \
uvx mcp-server-qdrant
```

Exposes a `qdrant-find` tool over stdio.

## Agents

Each search strategy is defined as a Claude Code sub-agent in `.claude/agents/`:

| Agent | Strategy | Engine | maxTurns |
|-------|----------|--------|----------|
| `dnd-5e-researcher` | BM25 simple | bm25s | 2 |
| `dnd-5e-researcher-keyword-expansion` | BM25 + LLM expansion | bm25s | 2 |
| `dnd-5e-researcher-2round` | BM25 2-round | bm25s | 4 |
| `dnd-5e-researcher-vector` | Vector DB naive | Qdrant | 2 |
| `dnd-5e-researcher-vector-2round` | Vector DB 2-round | Qdrant | 4 |

All agents are strictly instructed to **only use information from search results** — no LLM knowledge fill-in. The `maxTurns` constraint enforces the search pattern (1-pass agents get 2 turns, 2-round agents get 4).

## Benchmark questions

The benchmark uses questions from [`questions.json`](questions.json), with varying difficulty levels:

| ID | Question | Difficulty |
|----|----------|------------|
| `q1_simple_stat` | What is the Armor Class of an Adult Red Dragon? | Simple |
| `q2_simple_ability` | What is the range and damage of a Young White Dragon's Cold Breath? | Simple |
| `q3_medium_spell` | Wizard casts Dominate Monster on Adult Red Dragon — what save? | Medium |
| `q4_medium_disease` | What disease can characters catch in Croaker Cave (Frozen Sick)? | Medium |
| `q5_complex_multistep` | Level 9 Wizard with 20 INT casts Fireball at 120ft — full breakdown | Complex |

Each question includes an `expected_answer`, `reasoning`, and `sources` for the arbiter to evaluate against.

## Project structure

```text
search_bench/
├── .claude/
│   └── agents/              # Claude Code sub-agent definitions (1 per strategy)
├── data/
│   └── bm25_index/          # Serialized BM25 index (generated)
├── docs/                    # PDF corpus (not included — bring your own)
├── tools/
│   ├── bm25_index.py        # Build BM25 index from PDFs
│   ├── bm25_search.py       # CLI search over BM25 index
│   ├── qdrant_index.py      # Build Qdrant vector index from PDFs
│   ├── pdf_utils.py         # PDF extraction + chunking (shared)
│   └── extract_page.py      # Extract a single page from a PDF
├── questions.json           # Benchmark questions with expected answers
├── scoring.md               # Full scoring rubric
├── pyproject.toml           # Python dependencies (uv)
└── package.json             # Node dependencies (yarn)
```

## Tools reference

| Script | Purpose | Usage |
|--------|---------|-------|
| `tools/bm25_index.py` | Index all PDFs into BM25 | `PYTHONIOENCODING=utf-8 uv run python tools/bm25_index.py` |
| `tools/bm25_search.py` | Search the BM25 index (CLI) | `PYTHONIOENCODING=utf-8 uv run python tools/bm25_search.py "query" --top-k 10` |
| `tools/qdrant_index.py` | Index all PDFs into Qdrant | `PYTHONIOENCODING=utf-8 uv run python tools/qdrant_index.py [--reset]` |
| `tools/extract_page.py` | Extract one page as Markdown | `PYTHONIOENCODING=utf-8 uv run python tools/extract_page.py <pdf> <page>` |

## Tech stack

| Component | Technology |
|-----------|------------|
| BM25 search | [`bm25s`](https://github.com/xhluca/bm25s) + PyStemmer |
| Vector search | [Qdrant](https://qdrant.tech/) + [`fastembed`](https://github.com/qdrant/fastembed) (all-MiniLM-L6-v2, 384 dims) |
| PDF parsing | [PyMuPDF](https://pymupdf.readthedocs.io/) + pymupdf4llm |
| LLM agents | Claude Sonnet (search) / Claude Opus (arbitration) |
| MCP servers | bm25s built-in MCP / [mcp-server-qdrant](https://github.com/qdrant/mcp-server-qdrant) |
| Python | 3.12, managed with [uv](https://docs.astral.sh/uv/) |
| TypeScript | tsx + yarn (tooling) |

## Windows note

On Windows, always prefix Python commands with `PYTHONIOENCODING=utf-8` to avoid encoding errors with PDF text output. On Linux/macOS this is typically not needed.

## License

[MIT](LICENSE)

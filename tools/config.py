"""Centralized configuration loader for search_bench.

Reads search_bench.json and derives all paths/names from it.
Resolution order: explicit path > SEARCH_BENCH_CONFIG env > auto-discover at project root.
"""

import json
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent

REQUIRED_KEYS = {
    "docs_dir",
    "collection_name",
    "stemmer_language",
    "qdrant_url",
    "embedding_model",
}

DEFAULTS = {
    "docs_dir": "./docs",
    "collection_name": "dnd5e_chunks",
    "stemmer_language": "english",
    "qdrant_url": "http://localhost:6333",
    "embedding_model": "nomic-ai/nomic-embed-text-v1.5",
    "pdf_backend": "pymupdf",
}


def _find_config_file() -> Path | None:
    """Auto-discover config file: env var, then project root."""
    env_path = os.environ.get("SEARCH_BENCH_CONFIG")
    if env_path:
        p = Path(env_path)
        if p.is_file():
            return p

    default = PROJECT_ROOT / "search_bench.json"
    if default.is_file():
        return default

    return None


def load_config(config_path: str | Path | None = None) -> dict:
    """Load config, resolve paths, derive index dirs.

    Args:
        config_path: Explicit path to config JSON. If None, auto-discovers.

    Returns:
        Dict with keys: docs_dir (Path), collection_name (str),
        bm25_index_dir (Path), qdrant_collection_name (str),
        qdrant_url (str), embedding_model (str).
    """
    if config_path is not None:
        config_file = Path(config_path)
        if not config_file.is_file():
            print(f"Config file not found: {config_file}", file=sys.stderr)
            sys.exit(1)
    else:
        config_file = _find_config_file()

    if config_file is not None:
        with open(config_file, encoding="utf-8") as f:
            raw = json.load(f)

        # Validate required keys
        missing = REQUIRED_KEYS - set(raw.keys())
        if missing:
            print(
                f"Config error: missing keys in {config_file}: {', '.join(sorted(missing))}",
                file=sys.stderr,
            )
            sys.exit(1)

        config_root = config_file.parent.resolve()
    else:
        # No config file found — use defaults
        print(
            "Warning: no config file found, using built-in defaults.", file=sys.stderr
        )
        raw = dict(DEFAULTS)
        config_root = PROJECT_ROOT.resolve()

    # Resolve paths relative to config file location
    docs_dir = (config_root / raw["docs_dir"]).resolve()
    collection_name = raw["collection_name"]

    # Derive BM25 index dir and Qdrant collection name from collection_name
    bm25_index_dir = (config_root / "data" / f"bm25_{collection_name}").resolve()
    qdrant_collection_name = collection_name

    # Optional keys with defaults
    pdf_backend = raw.get("pdf_backend", DEFAULTS["pdf_backend"])
    if pdf_backend not in ("pymupdf", "marker"):
        print(
            f"Config error: pdf_backend must be 'pymupdf' or 'marker', got '{pdf_backend}'",
            file=sys.stderr,
        )
        sys.exit(1)

    return {
        "docs_dir": docs_dir,
        "collection_name": collection_name,
        "bm25_index_dir": bm25_index_dir,
        "qdrant_collection_name": qdrant_collection_name,
        "stemmer_language": raw["stemmer_language"],
        "qdrant_url": raw["qdrant_url"],
        "embedding_model": raw["embedding_model"],
        "pdf_backend": pdf_backend,
    }

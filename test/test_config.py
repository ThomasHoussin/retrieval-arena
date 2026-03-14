"""Unit tests for tools/config.py.

Strategy
--------
- load_config is tested with real temporary JSON files so the full path
  resolution, key validation, and derived-field logic are exercised.
- sys.exit calls (validation failures) are caught with pytest.raises(SystemExit).
- The SEARCH_BENCH_CONFIG env var and the project-root auto-discovery path are
  isolated via monkeypatch so tests never interact with the real config file.
"""

import json
import os
import sys
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Ensure project root is on sys.path (also done by conftest, but explicit here
# so the file is self-contained when run in isolation).
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.config import DEFAULTS, load_config


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

MINIMAL_REQUIRED = {
    "docs_dir": "./docs",
    "collection_name": "test_collection",
    "stemmer_language": "english",
    "qdrant_url": "http://localhost:6333",
    "embedding_model": "nomic-ai/nomic-embed-text-v1.5",
}


def _write_config(tmp_path: Path, data: dict) -> Path:
    """Write a JSON config file and return its path."""
    cfg = tmp_path / "search_bench.json"
    cfg.write_text(json.dumps(data), encoding="utf-8")
    return cfg


# ===========================================================================
# load_config — explicit path argument
# ===========================================================================


class TestLoadConfigExplicitPath:
    """Tests using an explicit config_path argument."""

    def test_exits_when_explicit_path_does_not_exist(self, tmp_path):
        missing = tmp_path / "nonexistent.json"
        with pytest.raises(SystemExit) as exc_info:
            load_config(config_path=missing)
        assert exc_info.value.code == 1

    def test_returns_dict_for_valid_config(self, tmp_path):
        cfg = _write_config(tmp_path, MINIMAL_REQUIRED)
        result = load_config(config_path=cfg)
        assert isinstance(result, dict)

    def test_docs_dir_resolved_to_absolute_path(self, tmp_path):
        cfg = _write_config(tmp_path, MINIMAL_REQUIRED)
        result = load_config(config_path=cfg)
        assert result["docs_dir"].is_absolute()

    def test_docs_dir_resolved_relative_to_config_file_location(self, tmp_path):
        data = {**MINIMAL_REQUIRED, "docs_dir": "./my_docs"}
        cfg = _write_config(tmp_path, data)
        result = load_config(config_path=cfg)
        assert result["docs_dir"] == (tmp_path / "my_docs").resolve()

    def test_bm25_index_dir_derived_from_collection_name(self, tmp_path):
        data = {**MINIMAL_REQUIRED, "collection_name": "mytest"}
        cfg = _write_config(tmp_path, data)
        result = load_config(config_path=cfg)
        assert result["bm25_index_dir"] == (tmp_path / "data" / "bm25_mytest").resolve()

    def test_qdrant_collection_name_equals_collection_name(self, tmp_path):
        data = {**MINIMAL_REQUIRED, "collection_name": "mytest"}
        cfg = _write_config(tmp_path, data)
        result = load_config(config_path=cfg)
        assert result["qdrant_collection_name"] == "mytest"

    def test_all_required_fields_present_in_result(self, tmp_path):
        cfg = _write_config(tmp_path, MINIMAL_REQUIRED)
        result = load_config(config_path=cfg)
        for key in ("docs_dir", "collection_name", "bm25_index_dir",
                    "qdrant_collection_name", "stemmer_language",
                    "qdrant_url", "embedding_model", "pdf_backend"):
            assert key in result, f"Missing key: {key}"

    def test_stemmer_language_passed_through(self, tmp_path):
        data = {**MINIMAL_REQUIRED, "stemmer_language": "french"}
        cfg = _write_config(tmp_path, data)
        result = load_config(config_path=cfg)
        assert result["stemmer_language"] == "french"

    def test_qdrant_url_passed_through(self, tmp_path):
        data = {**MINIMAL_REQUIRED, "qdrant_url": "http://remote-host:6333"}
        cfg = _write_config(tmp_path, data)
        result = load_config(config_path=cfg)
        assert result["qdrant_url"] == "http://remote-host:6333"

    def test_embedding_model_passed_through(self, tmp_path):
        data = {**MINIMAL_REQUIRED, "embedding_model": "custom/model-v2"}
        cfg = _write_config(tmp_path, data)
        result = load_config(config_path=cfg)
        assert result["embedding_model"] == "custom/model-v2"


# ===========================================================================
# load_config — pdf_backend handling
# ===========================================================================


class TestLoadConfigPdfBackend:
    """Tests specifically for the pdf_backend optional key."""

    def test_pdf_backend_defaults_to_pymupdf_when_absent(self, tmp_path):
        # MINIMAL_REQUIRED does not include pdf_backend
        cfg = _write_config(tmp_path, MINIMAL_REQUIRED)
        result = load_config(config_path=cfg)
        assert result["pdf_backend"] == "pymupdf"

    def test_pdf_backend_pymupdf_accepted(self, tmp_path):
        data = {**MINIMAL_REQUIRED, "pdf_backend": "pymupdf"}
        cfg = _write_config(tmp_path, data)
        result = load_config(config_path=cfg)
        assert result["pdf_backend"] == "pymupdf"

    def test_pdf_backend_marker_accepted(self, tmp_path):
        data = {**MINIMAL_REQUIRED, "pdf_backend": "marker"}
        cfg = _write_config(tmp_path, data)
        result = load_config(config_path=cfg)
        assert result["pdf_backend"] == "marker"

    def test_pdf_backend_invalid_value_exits(self, tmp_path):
        data = {**MINIMAL_REQUIRED, "pdf_backend": "invalid_backend"}
        cfg = _write_config(tmp_path, data)
        with pytest.raises(SystemExit) as exc_info:
            load_config(config_path=cfg)
        assert exc_info.value.code == 1

    def test_pdf_backend_uppercase_rejected(self, tmp_path):
        # Validation is case-sensitive; "PyMuPDF" is not a valid value
        data = {**MINIMAL_REQUIRED, "pdf_backend": "PyMuPDF"}
        cfg = _write_config(tmp_path, data)
        with pytest.raises(SystemExit) as exc_info:
            load_config(config_path=cfg)
        assert exc_info.value.code == 1

    def test_pdf_backend_empty_string_rejected(self, tmp_path):
        data = {**MINIMAL_REQUIRED, "pdf_backend": ""}
        cfg = _write_config(tmp_path, data)
        with pytest.raises(SystemExit) as exc_info:
            load_config(config_path=cfg)
        assert exc_info.value.code == 1


# ===========================================================================
# load_config — required key validation
# ===========================================================================


class TestLoadConfigRequiredKeyValidation:
    """Verify that missing required keys cause a controlled exit."""

    @pytest.mark.parametrize("missing_key", [
        "docs_dir",
        "collection_name",
        "stemmer_language",
        "qdrant_url",
        "embedding_model",
    ])
    def test_missing_required_key_exits(self, tmp_path, missing_key):
        data = {k: v for k, v in MINIMAL_REQUIRED.items() if k != missing_key}
        cfg = _write_config(tmp_path, data)
        with pytest.raises(SystemExit) as exc_info:
            load_config(config_path=cfg)
        assert exc_info.value.code == 1

    def test_all_required_keys_present_does_not_exit(self, tmp_path):
        cfg = _write_config(tmp_path, MINIMAL_REQUIRED)
        # Must not raise
        load_config(config_path=cfg)


# ===========================================================================
# load_config — auto-discovery via SEARCH_BENCH_CONFIG env var
# ===========================================================================


class TestLoadConfigEnvVar:
    """Verify that SEARCH_BENCH_CONFIG is honoured when no explicit path given."""

    def test_env_var_config_is_loaded(self, tmp_path, monkeypatch):
        cfg = _write_config(tmp_path, MINIMAL_REQUIRED)
        monkeypatch.setenv("SEARCH_BENCH_CONFIG", str(cfg))
        result = load_config()
        assert result["collection_name"] == MINIMAL_REQUIRED["collection_name"]

    def test_env_var_nonexistent_file_falls_back_to_defaults(self, tmp_path, monkeypatch):
        # If SEARCH_BENCH_CONFIG points to a missing file, _find_config_file returns
        # None and load_config uses built-in defaults (no sys.exit).
        monkeypatch.setenv("SEARCH_BENCH_CONFIG", str(tmp_path / "missing.json"))
        # Also block the project-root default so it does not interfere
        monkeypatch.setattr("tools.config.PROJECT_ROOT", tmp_path)
        result = load_config()
        assert result["pdf_backend"] == DEFAULTS["pdf_backend"]

    def test_env_var_takes_precedence_over_project_root_default(self, tmp_path, monkeypatch):
        env_cfg = tmp_path / "env_config.json"
        env_cfg.write_text(
            json.dumps({**MINIMAL_REQUIRED, "collection_name": "env_collection"}),
            encoding="utf-8",
        )
        root_cfg = tmp_path / "root_config.json"
        root_cfg.write_text(
            json.dumps({**MINIMAL_REQUIRED, "collection_name": "root_collection"}),
            encoding="utf-8",
        )
        monkeypatch.setenv("SEARCH_BENCH_CONFIG", str(env_cfg))
        monkeypatch.setattr("tools.config.PROJECT_ROOT", tmp_path)
        result = load_config()
        assert result["collection_name"] == "env_collection"


# ===========================================================================
# load_config — no config file found (use built-in defaults)
# ===========================================================================


class TestLoadConfigDefaults:
    """Verify behaviour when no config file is discoverable."""

    def test_uses_defaults_when_no_config_file(self, tmp_path, monkeypatch):
        monkeypatch.delenv("SEARCH_BENCH_CONFIG", raising=False)
        # Point PROJECT_ROOT to tmp_path which has no search_bench.json
        monkeypatch.setattr("tools.config.PROJECT_ROOT", tmp_path)
        result = load_config()
        assert result["pdf_backend"] == DEFAULTS["pdf_backend"]

    def test_default_pdf_backend_is_pymupdf(self, tmp_path, monkeypatch):
        monkeypatch.delenv("SEARCH_BENCH_CONFIG", raising=False)
        monkeypatch.setattr("tools.config.PROJECT_ROOT", tmp_path)
        result = load_config()
        assert result["pdf_backend"] == "pymupdf"

    def test_default_collection_name_used(self, tmp_path, monkeypatch):
        monkeypatch.delenv("SEARCH_BENCH_CONFIG", raising=False)
        monkeypatch.setattr("tools.config.PROJECT_ROOT", tmp_path)
        result = load_config()
        assert result["collection_name"] == DEFAULTS["collection_name"]

    def test_bm25_index_dir_derived_from_default_collection_name(self, tmp_path, monkeypatch):
        monkeypatch.delenv("SEARCH_BENCH_CONFIG", raising=False)
        monkeypatch.setattr("tools.config.PROJECT_ROOT", tmp_path)
        result = load_config()
        expected_name = f"bm25_{DEFAULTS['collection_name']}"
        assert result["bm25_index_dir"].name == expected_name

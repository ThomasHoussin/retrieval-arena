"""Tests for tools/finalize_neph.py: PJ mask alignment, final validation, generated README and manifest."""

import hashlib
import json

import bm25s
import numpy as np
import pytest
import Stemmer

import finalize_neph
from bm25_index import build_bm25_index
from finalize_neph import make_pj_mask, validate_corpus
from doc_utils import _extract_rtf
from rebuild_neph import configuration, write_json


def test_mask_is_aligned_float32_and_matches_full_path_case_insensitively():
    paths = [
        "PJ/book.pdf",
        "MJ - scenarios/book.pdf",
        "AdJ/mJ/book.pdf",
        "PJ/notes-MJ.pdf",
        "neutral/book.pdf",
        "PJ/book.pdf",
    ]
    mask = make_pj_mask([{"source": p} for p in paths])
    assert mask.dtype == np.float32 and mask.shape == (6,)
    assert mask.tolist() == [1, 0, 0, 0, 1, 1]


def test_rtf_shape_fallback_does_not_duplicate_legacy_representation(tmp_path):
    source = tmp_path / "shape.rtf"
    source.write_text(
        r"{\rtf1\ansi{\shp{\*\shpinst{\sp{\sn name}{\sv ignore}}"
        r"{\shptxt Nom : {\b Hydre}\par Force : 12}}"
        r"{\shprslt{\*\do{\dptxbxtext Nom : Hydre Force : 12}}}}}",
        encoding="utf-8",
    )
    pages = _extract_rtf(source)
    assert pages == [(1, "Nom : Hydre\nForce : 12")]


def test_validation_detects_changed_source_unresolved_empty_and_wrong_count(tmp_path):
    source = tmp_path / "book.txt"
    source.write_text("magie", encoding="utf-8")
    report = {
        "files": [
            {
                "source": "book.txt",
                "status": "extracted",
                "chunks": 1,
                "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
            }
        ],
        "discovered_files": 1,
        "total_chunks": 1,
    }
    corpus = [{"source": "book.txt", "text": "magie", "chunk_id": 0, "pages": [1]}]
    assert list(validate_corpus(corpus, report, tmp_path)) == ["book.txt"]
    report["files"][0]["status"] = "empty_pending_review"
    with pytest.raises(ValueError, match="Unresolved extraction"):
        validate_corpus(corpus, report, tmp_path)
    report["files"][0]["status"] = "extracted"
    report["files"][0]["chunks"] = 2
    with pytest.raises(ValueError, match="Chunk count mismatch"):
        validate_corpus(corpus, report, tmp_path)
    source.write_text("changed", encoding="utf-8")
    with pytest.raises(ValueError, match="Source changed"):
        validate_corpus(corpus, report, tmp_path)


@pytest.mark.parametrize("pipeline", ["neph-bm25-v1", "neph-bm25-v2"])
def test_finalized_notice_matches_build_version(tmp_path, monkeypatch, pipeline):
    source, output = tmp_path / "source", tmp_path / "index"
    source.mkdir()
    output.mkdir()
    document = source / "Éveil - 3e édition.txt"
    document.write_text("magie alchimie", encoding="utf-8")
    corpus = [
        {"source": document.name, "text": "magie alchimie", "pages": [1], "chunk_id": 0}
    ]
    cfg = configuration(source, output)
    cfg["pipeline"] = pipeline
    if pipeline == "neph-bm25-v1":
        retriever = bm25s.BM25()
        retriever.index(
            bm25s.tokenize([corpus[0]["text"]], stemmer=Stemmer.Stemmer("french"))
        )
        retriever.save(str(output), corpus=corpus)
    else:
        build_bm25_index(corpus, {**cfg, "bm25_index_dir": output})
    write_json(output / "build_config.json", cfg)
    write_json(output / "index_built.json", {"status": "index_built_pending_review"})
    write_json(
        output / "ingestion_report.json",
        {
            "config": cfg,
            "versions": {},
            "discovered_files": 1,
            "total_chunks": 1,
            "files": [
                {
                    "source": document.name,
                    "sha256": hashlib.sha256(document.read_bytes()).hexdigest(),
                    "status": "extracted",
                    "chunks": 1,
                }
            ],
        },
    )
    monkeypatch.setattr(finalize_neph, "version", lambda name: "test")
    finalize_neph.finalize(output)
    notice = (output / "README.md").read_text(encoding="utf-8")
    assert ("Seul `text` est indexé." in notice) == (pipeline == "neph-bm25-v1")
    assert ("Le nom du fichier sans extension" in notice) == (
        pipeline == "neph-bm25-v2"
    )
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["configuration"]["pipeline"] == pipeline
    assert np.load(output / "mask_pj.npy").tolist() == [1.0]


def test_coverage_notes_come_from_report_and_cache_engine(tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    engine = {
        "marker-pdf": "2.0.0",
        "surya-ocr": "0.22.1",
        "config": {"force_ocr": True},
    }
    write_json(cache / "abc_marker.json", {"pages": [[1, "texte"]], "engine": engine})
    write_json(cache / "def_marker.json", {"pages": [[1, "texte"]]})
    report = {
        "config": {"cache_dir": str(cache)},
        "files": [
            {
                "source": "MJ/new.pdf",
                "status": "extracted",
                "sha1": "abc",
                "cache_backend": "marker",
            },
            {
                "source": "MJ/old.pdf",
                "status": "extracted",
                "sha1": "def",
                "cache_backend": "marker",
            },
            {
                "source": "PJ/sheet.pdf",
                "status": "excluded_after_review",
                "review_note": "vide",
            },
            {"source": "img.jpg", "status": "ignored"},
        ],
    }
    overrides = finalize_neph.ocr_overrides(report)
    assert overrides == {"MJ/new.pdf": engine}
    stats = {"statuses": {"extracted": 2, "excluded_after_review": 1, "ignored": 1}}
    notes = finalize_neph.coverage_notes(
        report, stats, overrides, {"MJ/new.pdf": [], "MJ/old.pdf": []}
    )
    assert "- `PJ/sheet.pdf` : vide" in notes
    assert "- `MJ/new.pdf` : marker-pdf 2.0.0, surya-ocr 0.22.1 (force_ocr)" in notes
    assert "MJ/old.pdf" not in notes
    assert "Les 1 fichiers" in notes and "CDA5_ADJ6" not in notes
    assert "Ar-Kaïm" not in notes

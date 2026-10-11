"""Offline ingestion tests; no real OCR or full corpus scan is performed."""

import base64
import hashlib
import json
from pathlib import Path
import subprocess
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import pymupdf

import doc_utils
import pdf_utils
import rebuild_neph as rebuild


@pytest.fixture
def isolated_cache(tmp_path, monkeypatch):
    cache = tmp_path / "cache"
    monkeypatch.setattr(pdf_utils, "CACHE_DIR", cache)
    monkeypatch.setattr(rebuild, "CACHE_DIR", cache)
    return cache


def test_epub_preserves_accents_and_uses_argument_list(tmp_path, monkeypatch):
    source = tmp_path / "L'Éveil & histoire.epub"
    source.touch()
    monkeypatch.setattr(doc_utils.shutil, "which", lambda _: "pandoc")
    execute = Mock(
        return_value=SimpleNamespace(stdout="Éveil\nChapitre premier\n", stderr="")
    )
    monkeypatch.setattr(doc_utils.subprocess, "run", execute)
    assert doc_utils.extract_text(source) == [(1, "Éveil\nChapitre premier")]
    args, kwargs = execute.call_args
    assert args[0][-1] == str(source.resolve())
    assert "--from=epub" in args[0]
    assert kwargs["check"] is True
    assert kwargs["encoding"] == "utf-8"


def test_epub_missing_dependency_and_failed_conversion(tmp_path, monkeypatch):
    source = tmp_path / "book.epub"
    source.touch()
    monkeypatch.setattr(doc_utils.shutil, "which", lambda _: None)
    with pytest.raises(RuntimeError, match="pandoc"):
        doc_utils.extract_text(source)
    monkeypatch.setattr(doc_utils.shutil, "which", lambda _: "pandoc")
    monkeypatch.setattr(
        doc_utils.subprocess,
        "run",
        Mock(side_effect=subprocess.CalledProcessError(1, "pandoc")),
    )
    with pytest.raises(subprocess.CalledProcessError):
        doc_utils.extract_text(source)


def test_word_uses_disposable_copy_and_preserves_table_text(tmp_path, monkeypatch):
    source = tmp_path / "L'Hydre.doc"
    source.write_bytes(b"original source")
    monkeypatch.setattr(doc_utils.sys, "platform", "win32")
    copies = []

    def execute(args, **kwargs):
        copy = Path(args[-1])
        copies.append(copy)
        assert copy != source and copy.read_bytes() == source.read_bytes()
        assert "-DocumentPath" in args
        text = "Métamorphe\rNom\x07Force\x07\rHydre\x0712\x07"
        return SimpleNamespace(stdout=base64.b64encode(text.encode("utf-8")))

    monkeypatch.setattr(doc_utils.subprocess, "run", execute)
    pages = doc_utils.extract_text(source)
    assert pages[0][0] == 1
    assert "Métamorphe" in pages[0][1]
    assert "Nom | Force" in pages[0][1] and "Hydre | 12" in pages[0][1]
    assert source.read_bytes() == b"original source"
    assert not copies[0].exists()


def test_cache_survives_source_rename(tmp_path, isolated_cache, monkeypatch):
    source = tmp_path / "old.epub"
    source.write_bytes(b"same bytes")
    extraction = Mock(return_value=[(1, "Éveil de Nephilim")])
    monkeypatch.setattr(doc_utils, "_extract_epub", extraction)
    assert pdf_utils.extract_text_by_page(source, retry_empty=True)[1] is False
    renamed = source.rename(tmp_path / "new.epub")
    details = {}
    assert (
        pdf_utils.extract_text_by_page(renamed, retry_empty=True, diagnostics=details)[
            1
        ]
        is True
    )
    assert details["steps"] == ["cache"]
    assert extraction.call_count == 1


def test_malformed_cache_is_replaced(tmp_path, isolated_cache):
    source = tmp_path / "text.txt"
    source.write_text("contenu valide", encoding="utf-8")
    isolated_cache.mkdir()
    sha1 = hashlib.sha1(source.read_bytes()).hexdigest()
    cache = pdf_utils._cache_file(sha1, "direct")
    cache.write_text('{"pages": [[1, 42]]}', encoding="utf-8")
    assert pdf_utils.extract_text_by_page(source) == ([(1, "contenu valide")], False)
    assert json.loads(cache.read_text(encoding="utf-8"))["pages"] == [
        [1, "contenu valide"]
    ]


def make_pdf(path, text=None):
    with pymupdf.open() as document:
        page = document.new_page()
        if text:
            page.insert_text((72, 72), text)
        document.save(path)


def test_empty_marker_cache_retries_then_recovers_native_text(
    tmp_path, isolated_cache, monkeypatch
):
    source = tmp_path / "native.pdf"
    make_pdf(source, "Texte natif accessible")
    sha1 = hashlib.sha1(source.read_bytes()).hexdigest()
    pdf_utils._save_cache(sha1, "marker", [])
    marker = Mock(return_value=[])
    monkeypatch.setattr(pdf_utils, "_extract_marker", marker)
    monkeypatch.setattr(pdf_utils, "_extract_surya_pdf", Mock(return_value=[]))
    details = {}
    pages, cached = pdf_utils.extract_text_by_page(
        source, "marker", retry_empty=True, diagnostics=details
    )
    assert not cached and "Texte natif" in pages[0][1]
    assert details["cache_state"] == "empty"
    assert details["steps"] == ["marker_auto", "native_text_fallback"]
    marker.assert_called_once_with(source)
    assert pdf_utils._load_cache(sha1, "marker") == pages


@pytest.mark.parametrize("recovered", [[(1, "Texte OCR")], []])
def test_empty_scan_attempts_forced_ocr(
    tmp_path, isolated_cache, monkeypatch, recovered
):
    source = tmp_path / "scan.pdf"
    make_pdf(source)
    marker = Mock(side_effect=[[], recovered])
    monkeypatch.setattr(pdf_utils, "_extract_marker", marker)
    direct = Mock(return_value=[(1, "Texte du formulaire")])
    monkeypatch.setattr(pdf_utils, "_extract_surya_pdf", direct)
    details = {}
    pages, cached = pdf_utils.extract_text_by_page(
        source, "marker", retry_empty=True, diagnostics=details
    )
    assert pages == (recovered or [(1, "Texte du formulaire")]) and not cached
    assert details["steps"] == [
        "marker_auto",
        "native_text_fallback",
        "marker_force_ocr",
    ] + (["surya_direct_ocr"] if not recovered else [])
    assert marker.call_args.kwargs == {"force_ocr": True}
    assert direct.call_count == (0 if recovered else 1)


def test_empty_rtf_cache_is_reprocessed(tmp_path, isolated_cache):
    source = tmp_path / "text.rtf"
    source.write_text(r"{\rtf1\ansi Texte retrouve}", encoding="utf-8")
    sha1 = hashlib.sha1(source.read_bytes()).hexdigest()
    pdf_utils._save_cache(sha1, "direct", [])
    assert pdf_utils.extract_text_by_page(source, retry_empty=True) == (
        [(1, "Texte retrouve")],
        False,
    )


def test_failed_run_records_every_file_and_reuses_completed_cache(
    tmp_path, isolated_cache, monkeypatch
):
    source, output = tmp_path / "source", tmp_path / "output"
    source.mkdir()
    (source / "a.txt").write_text("magie alchimie", encoding="utf-8")
    (source / "b.epub").write_bytes(b"epub")
    (source / "image.jpg").write_bytes(b"image")
    extraction = Mock(side_effect=RuntimeError("broken epub"))
    monkeypatch.setattr(doc_utils, "_extract_epub", extraction)
    builder = Mock()
    monkeypatch.setattr(rebuild, "build_index", builder)
    with pytest.raises(RuntimeError, match="Extraction errors"):
        rebuild.run(source, output, preflight=False)
    report = json.loads((output / "ingestion_report.json").read_text(encoding="utf-8"))
    assert report["status"] == "failed" and len(report["files"]) == 3
    assert report["totals"] == {"extracted": 1, "error": 1, "ignored": 1}
    builder.assert_not_called()
    assert not (output / "index_built.json").exists()
    extraction.side_effect = None
    extraction.return_value = [(1, "roman retrouvé")]
    report = rebuild.run(source, output, preflight=False)
    assert report["files"][0]["cached"] is True
    assert report["status"] == "index_built_pending_review"
    builder.assert_called_once()
    with pytest.raises(RuntimeError, match="refusing to overwrite"):
        rebuild.run(source, output, preflight=False)


def test_interruption_writes_report_and_rerun_uses_cache(
    tmp_path, isolated_cache, monkeypatch
):
    source, output = tmp_path / "source", tmp_path / "output"
    source.mkdir()
    (source / "a.txt").write_text("magie", encoding="utf-8")
    (source / "b.epub").write_bytes(b"epub")
    extraction = Mock(side_effect=KeyboardInterrupt)
    monkeypatch.setattr(doc_utils, "_extract_epub", extraction)
    monkeypatch.setattr(rebuild, "build_index", Mock())
    with pytest.raises(KeyboardInterrupt):
        rebuild.run(source, output, preflight=False)
    report = json.loads((output / "ingestion_report.json").read_text(encoding="utf-8"))
    assert report["status"] == "interrupted"
    extraction.side_effect = None
    extraction.return_value = [(1, "Éveil")]
    report = rebuild.run(source, output, preflight=False)
    assert report["files"][0]["cached"] is True


def test_small_real_bm25_build_keeps_duplicate_paths_and_defers_mask(
    tmp_path, isolated_cache
):
    import bm25s

    source, output = tmp_path / "source", tmp_path / "output"
    for directory in ("PJ", "MJ"):
        folder = source / directory
        folder.mkdir(parents=True)
        (folder / "livre.txt").write_text("magie alchimie soleil", encoding="utf-8")
    (source / "empty.txt").touch()
    report = rebuild.run(source, output, preflight=False)
    loaded = bm25s.BM25.load(str(output), load_corpus=True)
    assert report["config"]["pipeline"] == "neph-bm25-v2"
    assert loaded.scores["num_docs"] == 2
    assert {row["source"] for row in loaded.corpus} == {"PJ/livre.txt", "MJ/livre.txt"}
    assert report["totals"]["empty_pending_review"] == 1
    assert not (output / "mask_pj.npy").exists()
    assert not (output / "manifest.json").exists()


def test_unknown_output_directory_is_preserved(tmp_path):
    source, output = tmp_path / "source", tmp_path / "output"
    source.mkdir()
    output.mkdir()
    existing = output / "params.index.json"
    existing.write_text("keep me", encoding="utf-8")
    with pytest.raises(RuntimeError, match="not an interrupted run"):
        rebuild.prepare_output(source, output)
    assert existing.read_text(encoding="utf-8") == "keep me"


def test_changed_source_prevents_index_build(tmp_path, isolated_cache, monkeypatch):
    source, output = tmp_path / "source", tmp_path / "output"
    source.mkdir()
    path = source / "text.txt"
    path.write_text("before", encoding="utf-8")

    def mutate(*args, **kwargs):
        path.write_text("after", encoding="utf-8")
        return [(1, "before")], False

    monkeypatch.setattr(rebuild, "extract_text_by_page", mutate)
    builder = Mock()
    monkeypatch.setattr(rebuild, "build_index", builder)
    with pytest.raises(RuntimeError, match="Extraction errors"):
        rebuild.run(source, output, preflight=False)
    builder.assert_not_called()


def test_v1_interrupted_build_cannot_resume_as_v2(tmp_path):
    source, output = tmp_path / "source", tmp_path / "output"
    source.mkdir()
    output.mkdir()
    config = rebuild.configuration(source, output)
    config["pipeline"] = "neph-bm25-v1"
    rebuild.write_json(output / "build_config.json", config)
    with pytest.raises(RuntimeError, match="not an interrupted run"):
        rebuild.prepare_output(source, output)
    assert json.loads((output / "build_config.json").read_text(encoding="utf-8")) == config

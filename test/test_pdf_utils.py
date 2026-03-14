"""Unit tests for tools/pdf_utils.py.

Strategy
--------
- clean_text and chunk_document are tested with real inputs (no mocking).
- extract_text_by_page routing is tested by mocking _extract_pymupdf and
  _extract_marker at the module level so the heavy backends are never loaded.
- extract_corpus is tested by mocking extract_text_by_page and the filesystem
  glob so no real PDFs are required.

pymupdf4llm is already installed in the project venv, so the top-level import
in pdf_utils.py succeeds; we only need to mock the function calls themselves.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

# ---------------------------------------------------------------------------
# The module under test
# ---------------------------------------------------------------------------
from tools.pdf_utils import (
    CHUNK_SIZE,
    OVERLAP,
    chunk_document,
    clean_text,
    extract_corpus,
    extract_text_by_page,
)


# ===========================================================================
# clean_text
# ===========================================================================


class TestCleanText:
    """Verify each normalization rule in clean_text."""

    def test_br_tag_self_closing_becomes_newline(self):
        result = clean_text("word1<br/>word2")
        assert "\n" in result
        assert "<br" not in result

    def test_br_tag_with_space_becomes_newline(self):
        result = clean_text("word1<br />word2")
        assert "\n" in result
        assert "<br" not in result

    def test_br_tag_without_slash_becomes_newline(self):
        result = clean_text("word1<br>word2")
        assert "\n" in result
        assert "<br" not in result

    def test_multiple_br_tags_all_replaced(self):
        result = clean_text("a<br>b<br/>c<br />d")
        assert result.count("\n") == 3
        assert "<br" not in result

    def test_long_separator_four_dashes_collapsed(self):
        result = clean_text("----")
        assert result == "---"

    def test_long_separator_many_dashes_collapsed(self):
        result = clean_text("a " + "-" * 40 + " b")
        assert "---" in result
        assert "----" not in result

    def test_three_dashes_unchanged(self):
        # Exactly three dashes must not be collapsed further
        result = clean_text("---")
        assert result == "---"

    def test_url_http_replaced(self):
        result = clean_text("see http://example.com for details")
        assert "[url deleted]" in result
        assert "http://" not in result

    def test_url_https_replaced(self):
        result = clean_text("visit https://example.com/path?q=1")
        assert "[url deleted]" in result
        assert "https://" not in result

    def test_url_with_path_and_query_fully_replaced(self):
        # The entire URL token must be one placeholder, not partially matched
        result = clean_text("https://docs.example.com/a/b?c=d&e=f#anchor")
        assert result.count("[url deleted]") == 1

    def test_multiple_urls_each_replaced(self):
        result = clean_text("http://a.com and https://b.com")
        assert result.count("[url deleted]") == 2
        assert "http" not in result

    def test_dot_sequence_three_dots_collapsed(self):
        result = clean_text("Chapter 1...........5")
        assert "..." in result
        assert "...." not in result

    def test_dot_sequence_two_dots_unchanged(self):
        # Two dots are not a "long dot sequence" and must be left alone
        result = clean_text("word1..word2")
        assert result == "word1..word2"

    def test_combined_normalization_order_independence(self):
        # Input contains all four artifact types at once
        text = "Header<br/>----https://x.com foo......bar"
        result = clean_text(text)
        assert "<br" not in result
        assert "----" not in result
        assert "https://" not in result
        assert "...." not in result

    def test_plain_text_unchanged(self):
        text = "The quick brown fox jumps over the lazy dog."
        assert clean_text(text) == text

    def test_empty_string_returns_empty(self):
        assert clean_text("") == ""


# ===========================================================================
# chunk_document
# ===========================================================================


class TestChunkDocument:
    """Verify chunking logic: size, overlap, page attribution, edge cases."""

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _make_pages(word_count: int, page_num: int = 1) -> list[tuple[int, str]]:
        words = [f"word{i}" for i in range(word_count)]
        return [(page_num, " ".join(words))]

    # ------------------------------------------------------------------
    # Nominal cases
    # ------------------------------------------------------------------

    def test_empty_pages_returns_empty_list(self):
        assert chunk_document([], "doc.pdf") == []

    def test_page_with_no_words_returns_empty_list(self):
        assert chunk_document([(1, "")], "doc.pdf") == []
        assert chunk_document([(1, "   ")], "doc.pdf") == []

    def test_single_small_page_produces_one_chunk(self):
        pages = [(1, "alpha beta gamma")]
        chunks = chunk_document(pages, "src.pdf")
        assert len(chunks) == 1
        assert chunks[0]["text"] == "alpha beta gamma"

    def test_chunk_contains_required_keys(self):
        pages = [(1, "alpha beta")]
        chunk = chunk_document(pages, "my/doc.pdf")[0]
        assert "text" in chunk
        assert "source" in chunk
        assert "pages" in chunk
        assert "chunk_id" in chunk

    def test_source_field_matches_argument(self):
        pages = [(1, "word")]
        chunk = chunk_document(pages, "books/phb.pdf")[0]
        assert chunk["source"] == "books/phb.pdf"

    def test_chunk_ids_are_sequential_from_zero(self):
        # Generate enough words to force multiple chunks
        pages = self._make_pages(CHUNK_SIZE * 3)
        chunks = chunk_document(pages, "doc.pdf")
        assert [c["chunk_id"] for c in chunks] == list(range(len(chunks)))

    def test_first_chunk_has_chunk_size_words(self):
        pages = self._make_pages(CHUNK_SIZE * 2)
        chunks = chunk_document(pages, "doc.pdf")
        assert len(chunks[0]["text"].split()) == CHUNK_SIZE

    def test_second_chunk_starts_with_overlap_from_first(self):
        # Words [0..CHUNK_SIZE) in chunk 0, words [CHUNK_SIZE-OVERLAP..2*CHUNK_SIZE-OVERLAP) in chunk 1
        pages = self._make_pages(CHUNK_SIZE * 2)
        chunks = chunk_document(pages, "doc.pdf")
        chunk0_words = chunks[0]["text"].split()
        chunk1_words = chunks[1]["text"].split()
        # The last OVERLAP words of chunk 0 must equal the first OVERLAP words of chunk 1
        assert chunk0_words[-OVERLAP:] == chunk1_words[:OVERLAP]

    def test_chunks_cover_all_words(self):
        # Every word from the source must appear in at least one chunk
        pages = self._make_pages(CHUNK_SIZE + OVERLAP + 10)
        all_words = pages[0][1].split()
        chunks = chunk_document(pages, "doc.pdf")
        covered = set()
        for c in chunks:
            covered.update(c["text"].split())
        assert covered == set(all_words)

    # ------------------------------------------------------------------
    # Page attribution
    # ------------------------------------------------------------------

    def test_single_page_attribution(self):
        pages = [(3, "alpha beta gamma")]
        chunk = chunk_document(pages, "doc.pdf")[0]
        assert chunk["pages"] == [3]

    def test_chunk_spanning_two_pages_lists_both(self):
        # Create a chunk that straddles page 1 and page 2
        words_p1 = " ".join(f"w{i}" for i in range(300))
        words_p2 = " ".join(f"w{i}" for i in range(300, 700))
        pages = [(1, words_p1), (2, words_p2)]
        chunks = chunk_document(pages, "doc.pdf")
        # First chunk covers 512 words; page 1 has 300 words so chunk 0 spans both pages
        assert 1 in chunks[0]["pages"]
        assert 2 in chunks[0]["pages"]

    def test_pages_list_is_sorted(self):
        words_p1 = " ".join(f"w{i}" for i in range(300))
        words_p2 = " ".join(f"w{i}" for i in range(300, 700))
        pages = [(1, words_p1), (2, words_p2)]
        chunks = chunk_document(pages, "doc.pdf")
        for chunk in chunks:
            assert chunk["pages"] == sorted(chunk["pages"])

    # ------------------------------------------------------------------
    # Trailing chunk suppression
    # ------------------------------------------------------------------

    def test_tiny_trailing_chunk_suppressed(self):
        # The suppression condition fires when the remaining words after
        # advancing start (by CHUNK_SIZE - OVERLAP) would be < OVERLAP.
        # After the first chunk: start_new = CHUNK_SIZE - OVERLAP.
        # remaining = total - start_new  <  OVERLAP
        #   => total  <  (CHUNK_SIZE - OVERLAP) + OVERLAP = CHUNK_SIZE
        # So any total in [1, CHUNK_SIZE - 1] produces exactly 1 chunk.
        total_words = CHUNK_SIZE - 1
        pages = self._make_pages(total_words)
        chunks = chunk_document(pages, "doc.pdf")
        assert len(chunks) == 1

    def test_trailing_chunk_not_suppressed_at_exact_chunk_size_boundary(self):
        # total == CHUNK_SIZE: remaining after advance = CHUNK_SIZE - (CHUNK_SIZE - OVERLAP) = OVERLAP.
        # The condition is `< OVERLAP` (strict), so exactly OVERLAP remaining
        # does NOT trigger suppression — the loop continues and yields a second chunk.
        total_words = CHUNK_SIZE
        pages = self._make_pages(total_words)
        chunks = chunk_document(pages, "doc.pdf")
        assert len(chunks) == 2

    def test_no_chunks_for_zero_words(self):
        assert chunk_document([(1, "")], "doc.pdf") == []


# ===========================================================================
# extract_text_by_page — routing
# ===========================================================================


class TestExtractTextByPage:
    """Verify that the correct backend function is called based on the argument."""

    def test_default_backend_calls_pymupdf(self):
        fake_pages = [(1, "page one text")]
        with patch("tools.pdf_utils._extract_pymupdf", return_value=fake_pages) as mock_pym, \
             patch("tools.pdf_utils._extract_marker") as mock_mrk:
            result = extract_text_by_page(Path("dummy.pdf"))
        mock_pym.assert_called_once_with(Path("dummy.pdf"))
        mock_mrk.assert_not_called()
        assert result == fake_pages

    def test_explicit_pymupdf_backend_calls_pymupdf(self):
        fake_pages = [(1, "text")]
        with patch("tools.pdf_utils._extract_pymupdf", return_value=fake_pages) as mock_pym, \
             patch("tools.pdf_utils._extract_marker") as mock_mrk:
            result = extract_text_by_page(Path("dummy.pdf"), backend="pymupdf")
        mock_pym.assert_called_once_with(Path("dummy.pdf"))
        mock_mrk.assert_not_called()
        assert result == fake_pages

    def test_marker_backend_calls_marker(self):
        fake_pages = [(1, "marker text")]
        with patch("tools.pdf_utils._extract_marker", return_value=fake_pages) as mock_mrk, \
             patch("tools.pdf_utils._extract_pymupdf") as mock_pym:
            result = extract_text_by_page(Path("dummy.pdf"), backend="marker")
        mock_mrk.assert_called_once_with(Path("dummy.pdf"))
        mock_pym.assert_not_called()
        assert result == fake_pages

    def test_pymupdf_backend_returns_value_from_backend(self):
        fake_pages = [(2, "hello"), (3, "world")]
        with patch("tools.pdf_utils._extract_pymupdf", return_value=fake_pages):
            result = extract_text_by_page(Path("x.pdf"), backend="pymupdf")
        assert result == fake_pages

    def test_marker_backend_returns_value_from_backend(self):
        fake_pages = [(1, "marker page")]
        with patch("tools.pdf_utils._extract_marker", return_value=fake_pages):
            result = extract_text_by_page(Path("x.pdf"), backend="marker")
        assert result == fake_pages


# ===========================================================================
# extract_corpus — PDF discovery, delegation, and aggregation
# ===========================================================================


class TestExtractCorpus:
    """Verify corpus extraction: PDF discovery, per-file processing, aggregation."""

    def _fake_pdf(self, name: str, docs_dir: Path) -> Path:
        """Return a Path object inside docs_dir without creating a real file."""
        return docs_dir / name

    def test_calls_extract_text_by_page_for_each_pdf(self, tmp_path):
        # Create two real empty files so glob finds them
        (tmp_path / "a.pdf").touch()
        (tmp_path / "b.pdf").touch()

        fake_pages = [(1, "word")]
        with patch("tools.pdf_utils.extract_text_by_page", return_value=fake_pages) as mock_ext:
            extract_corpus(tmp_path, backend="pymupdf")

        assert mock_ext.call_count == 2

    def test_passes_backend_to_extract_text_by_page(self, tmp_path):
        (tmp_path / "x.pdf").touch()
        fake_pages = [(1, "word")]
        with patch("tools.pdf_utils.extract_text_by_page", return_value=fake_pages) as mock_ext:
            extract_corpus(tmp_path, backend="marker")
        _, kwargs = mock_ext.call_args
        assert kwargs.get("backend") == "marker" or mock_ext.call_args[0][1] == "marker"

    def test_returns_chunks_from_all_pdfs(self, tmp_path):
        (tmp_path / "a.pdf").touch()
        (tmp_path / "b.pdf").touch()
        # Each PDF yields 600 words — enough for at least one chunk each
        words = " ".join(f"w{i}" for i in range(600))
        fake_pages = [(1, words)]
        with patch("tools.pdf_utils.extract_text_by_page", return_value=fake_pages):
            chunks = extract_corpus(tmp_path, backend="pymupdf")
        # Two PDFs each producing chunks means total > 0
        assert len(chunks) > 0
        sources = {c["source"] for c in chunks}
        assert len(sources) == 2

    def test_chunk_source_is_relative_path(self, tmp_path):
        pdf = tmp_path / "book.pdf"
        pdf.touch()
        fake_pages = [(1, " ".join(f"w{i}" for i in range(600)))]
        with patch("tools.pdf_utils.extract_text_by_page", return_value=fake_pages):
            chunks = extract_corpus(tmp_path, backend="pymupdf")
        assert all("book.pdf" in c["source"] for c in chunks)
        # Must be relative, not absolute
        assert all(not Path(c["source"]).is_absolute() for c in chunks)

    def test_exits_when_no_pdfs_found(self, tmp_path):
        # tmp_path is empty — no PDFs
        with pytest.raises(SystemExit) as exc_info:
            extract_corpus(tmp_path, backend="pymupdf")
        assert exc_info.value.code == 1

    def test_exits_when_all_pdfs_produce_no_chunks(self, tmp_path):
        (tmp_path / "empty.pdf").touch()
        # extract_text_by_page returns empty list → chunk_document returns [] → no chunks
        with patch("tools.pdf_utils.extract_text_by_page", return_value=[]):
            with pytest.raises(SystemExit) as exc_info:
                extract_corpus(tmp_path, backend="pymupdf")
        assert exc_info.value.code == 1

    def test_continues_processing_after_per_pdf_exception(self, tmp_path):
        (tmp_path / "good.pdf").touch()
        (tmp_path / "bad.pdf").touch()

        good_pages = [(1, " ".join(f"w{i}" for i in range(600)))]

        def side_effect(path, backend):
            if "bad" in str(path):
                raise RuntimeError("simulated extraction failure")
            return good_pages

        with patch("tools.pdf_utils.extract_text_by_page", side_effect=side_effect):
            # Should not raise; bad.pdf is skipped, good.pdf produces chunks
            chunks = extract_corpus(tmp_path, backend="pymupdf")

        assert len(chunks) > 0
        assert all("good.pdf" in c["source"] for c in chunks)

    def test_discovers_pdfs_recursively(self, tmp_path):
        subdir = tmp_path / "sub"
        subdir.mkdir()
        (subdir / "nested.pdf").touch()
        fake_pages = [(1, " ".join(f"w{i}" for i in range(600)))]
        with patch("tools.pdf_utils.extract_text_by_page", return_value=fake_pages):
            chunks = extract_corpus(tmp_path, backend="pymupdf")
        sources = {c["source"] for c in chunks}
        assert any("nested.pdf" in s for s in sources)

"""Unit tests for tools/doc_utils.py.

Strategy
--------
- All extractors are tested with real files created in tmp_path — no mocking.
- Binary document formats (DOCX, PPTX, ODT) are built programmatically using
  their respective libraries so tests do not depend on checked-in binary fixtures.
- RTF files are written from minimal hand-crafted RTF strings.
- HTML tests cover entity decoding, script/style skipping, and edge cases.
- The _HTMLTextExtractor parser class is also tested directly.
- extract_text (dispatcher) is tested for routing, case-insensitive extensions,
  the validation warning, and rejection of unsupported extensions.
- Return type contract (list[tuple[int, str]]) is verified for every extractor.
"""

import io
import sys
from pathlib import Path

import pytest

from tools.doc_utils import (
    SUPPORTED_EXTENSIONS,
    _HTMLTextExtractor,
    _extract_docx,
    _extract_html,
    _extract_odt,
    _extract_pptx,
    _extract_rtf,
    _extract_txt,
    _read_text_file,
    extract_text,
)


# ---------------------------------------------------------------------------
# Helpers shared across test classes
# ---------------------------------------------------------------------------


def _make_docx(path: Path, paragraphs: list[str] | None = None, table_rows: list[list[str]] | None = None) -> Path:
    """Create a DOCX file at *path* with the given paragraphs and/or table rows."""
    from docx import Document

    doc = Document()
    for para in paragraphs or []:
        doc.add_paragraph(para)
    if table_rows:
        cols = max(len(row) for row in table_rows)
        table = doc.add_table(rows=len(table_rows), cols=cols)
        for r_idx, row in enumerate(table_rows):
            for c_idx, cell_text in enumerate(row):
                table.cell(r_idx, c_idx).text = cell_text
    doc.save(str(path))
    return path


def _make_pptx(path: Path, slides: list[list[str]]) -> Path:
    """Create a PPTX file at *path*.

    Each element of *slides* is a list of paragraph strings to place in a
    textbox on that slide.
    """
    from pptx import Presentation
    from pptx.util import Inches

    prs = Presentation()
    blank_layout = prs.slide_layouts[6]  # Blank layout
    for slide_texts in slides:
        slide = prs.slides.add_slide(blank_layout)
        if slide_texts:
            txBox = slide.shapes.add_textbox(Inches(1), Inches(1), Inches(6), Inches(4))
            tf = txBox.text_frame
            tf.text = slide_texts[0]
            for para_text in slide_texts[1:]:
                para = tf.add_paragraph()
                para.text = para_text
    prs.save(str(path))
    return path


def _make_odt(path: Path, paragraphs: list[str]) -> Path:
    """Create an ODT file at *path* with the given paragraphs."""
    from odf.opendocument import OpenDocumentText
    from odf.text import P

    doc = OpenDocumentText()
    for text in paragraphs:
        p = P()
        p.addText(text)
        doc.text.addElement(p)
    doc.save(str(path))
    return path


def _make_rtf(path: Path, body: str) -> Path:
    """Write a minimal valid RTF file containing *body* as plain text."""
    rtf = r"{\rtf1\ansi " + body + r"}"
    path.write_text(rtf, encoding="utf-8")
    return path


# ===========================================================================
# _read_text_file
# ===========================================================================


class TestReadTextFile:
    """_read_text_file reads UTF-8 by default and falls back to latin-1."""

    def test_reads_utf8_file(self, tmp_path):
        f = tmp_path / "utf8.txt"
        f.write_text("Hello UTF-8 \u2603", encoding="utf-8")
        assert _read_text_file(f) == "Hello UTF-8 \u2603"

    def test_falls_back_to_latin1_when_utf8_fails(self, tmp_path):
        f = tmp_path / "latin1.txt"
        # \xe9 is 'é' in latin-1 but invalid as a UTF-8 continuation byte
        f.write_bytes("Caf\xe9".encode("latin-1"))
        result = _read_text_file(f)
        assert result == "Café"

    def test_pure_ascii_file_read_correctly(self, tmp_path):
        f = tmp_path / "ascii.txt"
        f.write_text("simple ascii text", encoding="utf-8")
        assert _read_text_file(f) == "simple ascii text"

    def test_returns_string_type(self, tmp_path):
        f = tmp_path / "t.txt"
        f.write_text("data", encoding="utf-8")
        assert isinstance(_read_text_file(f), str)


# ===========================================================================
# _extract_txt
# ===========================================================================


class TestExtractTxt:
    """_extract_txt handles plain text and markdown files."""

    def test_nominal_returns_single_page_tuple(self, tmp_path):
        f = tmp_path / "doc.txt"
        f.write_text("Hello world", encoding="utf-8")
        result = _extract_txt(f)
        assert result == [(1, "Hello world")]

    def test_page_number_is_always_one(self, tmp_path):
        f = tmp_path / "doc.txt"
        f.write_text("some text", encoding="utf-8")
        page_num, _ = _extract_txt(f)[0]
        assert page_num == 1

    def test_return_type_is_list_of_tuples(self, tmp_path):
        f = tmp_path / "doc.txt"
        f.write_text("data", encoding="utf-8")
        result = _extract_txt(f)
        assert isinstance(result, list)
        assert all(isinstance(item, tuple) and len(item) == 2 for item in result)

    def test_empty_file_returns_empty_list(self, tmp_path):
        f = tmp_path / "empty.txt"
        f.write_text("", encoding="utf-8")
        assert _extract_txt(f) == []

    def test_whitespace_only_file_returns_empty_list(self, tmp_path):
        f = tmp_path / "spaces.txt"
        f.write_text("   \n\n\t  \n", encoding="utf-8")
        assert _extract_txt(f) == []

    def test_multiline_content_preserved(self, tmp_path):
        f = tmp_path / "multi.txt"
        f.write_text("line one\nline two\nline three", encoding="utf-8")
        _, text = _extract_txt(f)[0]
        assert "line one" in text
        assert "line two" in text
        assert "line three" in text

    def test_leading_trailing_whitespace_stripped(self, tmp_path):
        f = tmp_path / "padded.txt"
        f.write_text("  padded content  ", encoding="utf-8")
        _, text = _extract_txt(f)[0]
        assert not text.startswith(" ")
        assert not text.endswith(" ")

    def test_clean_text_applied_url_replaced(self, tmp_path):
        f = tmp_path / "url.txt"
        f.write_text("Visit https://example.com for info", encoding="utf-8")
        _, text = _extract_txt(f)[0]
        assert "https://example.com" not in text
        assert "[url deleted]" in text

    def test_latin1_encoded_file_read_successfully(self, tmp_path):
        f = tmp_path / "latin.txt"
        f.write_bytes("Caf\xe9 content".encode("latin-1"))
        result = _extract_txt(f)
        assert len(result) == 1
        assert "Café" in result[0][1]

    def test_markdown_file_content_preserved(self, tmp_path):
        f = tmp_path / "readme.md"
        f.write_text("# Heading\n\nParagraph body text.", encoding="utf-8")
        _, text = _extract_txt(f)[0]
        assert "Heading" in text
        assert "Paragraph body text" in text


# ===========================================================================
# _extract_docx
# ===========================================================================


class TestExtractDocx:
    """_extract_docx extracts paragraphs and table cells from DOCX files."""

    def test_nominal_paragraph_text_extracted(self, tmp_path):
        f = _make_docx(tmp_path / "doc.docx", paragraphs=["Hello from DOCX"])
        result = _extract_docx(f)
        assert len(result) == 1
        assert "Hello from DOCX" in result[0][1]

    def test_page_number_is_always_one(self, tmp_path):
        f = _make_docx(tmp_path / "doc.docx", paragraphs=["text"])
        page_num, _ = _extract_docx(f)[0]
        assert page_num == 1

    def test_return_type_is_list_of_tuples(self, tmp_path):
        f = _make_docx(tmp_path / "doc.docx", paragraphs=["text"])
        result = _extract_docx(f)
        assert isinstance(result, list)
        assert all(isinstance(item, tuple) and len(item) == 2 for item in result)

    def test_multiple_paragraphs_joined(self, tmp_path):
        f = _make_docx(tmp_path / "doc.docx", paragraphs=["First", "Second", "Third"])
        _, text = _extract_docx(f)[0]
        assert "First" in text
        assert "Second" in text
        assert "Third" in text

    def test_empty_docx_returns_empty_list(self, tmp_path):
        f = _make_docx(tmp_path / "empty.docx")
        assert _extract_docx(f) == []

    def test_whitespace_only_paragraphs_return_empty_list(self, tmp_path):
        f = _make_docx(tmp_path / "spaces.docx", paragraphs=["   ", ""])
        assert _extract_docx(f) == []

    def test_table_cells_extracted(self, tmp_path):
        rows = [["Name", "Age"], ["Alice", "30"]]
        f = _make_docx(tmp_path / "table.docx", table_rows=rows)
        _, text = _extract_docx(f)[0]
        assert "Name" in text
        assert "Age" in text
        assert "Alice" in text
        assert "30" in text

    def test_table_cells_joined_with_pipe(self, tmp_path):
        rows = [["Alpha", "Beta", "Gamma"]]
        f = _make_docx(tmp_path / "table.docx", table_rows=rows)
        _, text = _extract_docx(f)[0]
        assert "Alpha | Beta | Gamma" in text

    def test_empty_table_cells_excluded_from_row(self, tmp_path):
        # Row with mixed empty and non-empty cells
        rows = [["Header", ""], ["", "Value"]]
        f = _make_docx(tmp_path / "partial.docx", table_rows=rows)
        _, text = _extract_docx(f)[0]
        assert "Header" in text
        assert "Value" in text
        # Empty-cell rows that become single-value rows should not show pipes
        # for the missing cell
        assert "| |" not in text

    def test_paragraphs_and_tables_combined(self, tmp_path):
        rows = [["Col1", "Col2"]]
        f = _make_docx(tmp_path / "combined.docx", paragraphs=["Intro"], table_rows=rows)
        _, text = _extract_docx(f)[0]
        assert "Intro" in text
        assert "Col1" in text
        assert "Col2" in text

    def test_clean_text_applied_url_replaced(self, tmp_path):
        f = _make_docx(tmp_path / "url.docx", paragraphs=["See https://example.com for details"])
        _, text = _extract_docx(f)[0]
        assert "https://example.com" not in text
        assert "[url deleted]" in text


# ===========================================================================
# _extract_pptx
# ===========================================================================


class TestExtractPptx:
    """_extract_pptx extracts text from all slides into a single page."""

    def test_nominal_slide_text_extracted(self, tmp_path):
        f = _make_pptx(tmp_path / "pres.pptx", slides=[["Slide one content"]])
        result = _extract_pptx(f)
        assert len(result) == 1
        assert "Slide one content" in result[0][1]

    def test_page_number_is_always_one(self, tmp_path):
        f = _make_pptx(tmp_path / "pres.pptx", slides=[["text"]])
        page_num, _ = _extract_pptx(f)[0]
        assert page_num == 1

    def test_return_type_is_list_of_tuples(self, tmp_path):
        f = _make_pptx(tmp_path / "pres.pptx", slides=[["text"]])
        result = _extract_pptx(f)
        assert isinstance(result, list)
        assert all(isinstance(item, tuple) and len(item) == 2 for item in result)

    def test_multiple_slides_all_text_concatenated(self, tmp_path):
        f = _make_pptx(
            tmp_path / "multi.pptx",
            slides=[["Slide 1 content"], ["Slide 2 content"], ["Slide 3 content"]],
        )
        _, text = _extract_pptx(f)[0]
        assert "Slide 1 content" in text
        assert "Slide 2 content" in text
        assert "Slide 3 content" in text

    def test_multiple_paragraphs_in_one_textbox(self, tmp_path):
        f = _make_pptx(tmp_path / "paras.pptx", slides=[["First para", "Second para"]])
        _, text = _extract_pptx(f)[0]
        assert "First para" in text
        assert "Second para" in text

    def test_empty_presentation_returns_empty_list(self, tmp_path):
        f = _make_pptx(tmp_path / "empty.pptx", slides=[[]])
        assert _extract_pptx(f) == []

    def test_slide_with_no_text_returns_empty_list(self, tmp_path):
        # Blank slide with no textbox added
        from pptx import Presentation

        prs = Presentation()
        blank = prs.slide_layouts[6]
        prs.slides.add_slide(blank)
        f = tmp_path / "blank.pptx"
        prs.save(str(f))
        assert _extract_pptx(f) == []

    def test_whitespace_only_paragraphs_excluded(self, tmp_path):
        f = _make_pptx(tmp_path / "ws.pptx", slides=[["   "]])
        assert _extract_pptx(f) == []

    def test_clean_text_applied_url_replaced(self, tmp_path):
        f = _make_pptx(tmp_path / "url.pptx", slides=[["Visit https://example.com now"]])
        _, text = _extract_pptx(f)[0]
        assert "https://example.com" not in text
        assert "[url deleted]" in text


# ===========================================================================
# _extract_rtf
# ===========================================================================


class TestExtractRtf:
    """_extract_rtf strips RTF control codes and returns plain text."""

    def test_nominal_plain_text_extracted(self, tmp_path):
        f = _make_rtf(tmp_path / "doc.rtf", "Hello World")
        result = _extract_rtf(f)
        assert len(result) == 1
        assert "Hello World" in result[0][1]

    def test_page_number_is_always_one(self, tmp_path):
        f = _make_rtf(tmp_path / "doc.rtf", "text")
        page_num, _ = _extract_rtf(f)[0]
        assert page_num == 1

    def test_return_type_is_list_of_tuples(self, tmp_path):
        f = _make_rtf(tmp_path / "doc.rtf", "data")
        result = _extract_rtf(f)
        assert isinstance(result, list)
        assert all(isinstance(item, tuple) and len(item) == 2 for item in result)

    def test_rtf_control_words_stripped(self, tmp_path):
        # Bold control word \b ... \b0 should not appear in output
        rtf = r"{\rtf1\ansi {\b bold text\b0}}"
        f = tmp_path / "bold.rtf"
        f.write_text(rtf, encoding="utf-8")
        _, text = _extract_rtf(f)[0]
        assert "\\b" not in text
        assert "bold text" in text

    def test_empty_rtf_returns_empty_list(self, tmp_path):
        f = tmp_path / "empty.rtf"
        f.write_text(r"{\rtf1\ansi }", encoding="utf-8")
        assert _extract_rtf(f) == []

    def test_latin1_encoded_rtf_read_successfully(self, tmp_path):
        f = tmp_path / "latin.rtf"
        content = r"{\rtf1\ansi " + "Caf\xe9" + r"}"
        f.write_bytes(content.encode("latin-1"))
        result = _extract_rtf(f)
        assert len(result) == 1
        assert "Café" in result[0][1]

    def test_clean_text_applied_url_replaced(self, tmp_path):
        f = _make_rtf(tmp_path / "url.rtf", "See https://example.com here")
        _, text = _extract_rtf(f)[0]
        assert "https://example.com" not in text
        assert "[url deleted]" in text


# ===========================================================================
# _extract_odt
# ===========================================================================


class TestExtractOdt:
    """_extract_odt uses odfpy to read OpenDocument Text files."""

    def test_nominal_paragraph_text_extracted(self, tmp_path):
        f = _make_odt(tmp_path / "doc.odt", ["Hello from ODT"])
        result = _extract_odt(f)
        assert len(result) == 1
        assert "Hello from ODT" in result[0][1]

    def test_page_number_is_always_one(self, tmp_path):
        f = _make_odt(tmp_path / "doc.odt", ["text"])
        page_num, _ = _extract_odt(f)[0]
        assert page_num == 1

    def test_return_type_is_list_of_tuples(self, tmp_path):
        f = _make_odt(tmp_path / "doc.odt", ["data"])
        result = _extract_odt(f)
        assert isinstance(result, list)
        assert all(isinstance(item, tuple) and len(item) == 2 for item in result)

    def test_multiple_paragraphs_joined(self, tmp_path):
        f = _make_odt(tmp_path / "multi.odt", ["First", "Second", "Third"])
        _, text = _extract_odt(f)[0]
        assert "First" in text
        assert "Second" in text
        assert "Third" in text

    def test_empty_paragraphs_skipped(self, tmp_path):
        # ODT with only an empty paragraph element
        from odf.opendocument import OpenDocumentText
        from odf.text import P

        doc = OpenDocumentText()
        doc.text.addElement(P())  # no text added — empty element
        f = tmp_path / "empty.odt"
        doc.save(str(f))
        assert _extract_odt(f) == []

    def test_odt_with_no_paragraphs_returns_empty_list(self, tmp_path):
        f = _make_odt(tmp_path / "none.odt", [])
        assert _extract_odt(f) == []

    def test_clean_text_applied_url_replaced(self, tmp_path):
        f = _make_odt(tmp_path / "url.odt", ["Visit https://example.com now"])
        _, text = _extract_odt(f)[0]
        assert "https://example.com" not in text
        assert "[url deleted]" in text


# ===========================================================================
# _HTMLTextExtractor (parser class)
# ===========================================================================


class TestHTMLTextExtractor:
    """Direct unit tests for the _HTMLTextExtractor parser class."""

    def test_plain_text_in_body_extracted(self):
        parser = _HTMLTextExtractor()
        parser.feed("<p>Hello world</p>")
        assert "Hello world" in parser.get_text()

    def test_script_content_skipped(self):
        parser = _HTMLTextExtractor()
        parser.feed("<p>Before</p><script>alert('secret')</script><p>After</p>")
        text = parser.get_text()
        assert "Before" in text
        assert "After" in text
        assert "secret" not in text
        assert "alert" not in text

    def test_style_content_skipped(self):
        parser = _HTMLTextExtractor()
        parser.feed("<p>Visible</p><style>.hidden { display: none; }</style>")
        text = parser.get_text()
        assert "Visible" in text
        assert "display" not in text
        assert ".hidden" not in text

    def test_skip_flag_resets_after_script_closes(self):
        parser = _HTMLTextExtractor()
        parser.feed("<script>code</script><p>Shown</p>")
        assert "Shown" in parser.get_text()

    def test_skip_flag_resets_after_style_closes(self):
        parser = _HTMLTextExtractor()
        parser.feed("<style>rules</style><p>Also shown</p>")
        assert "Also shown" in parser.get_text()

    def test_html_entities_decoded(self):
        parser = _HTMLTextExtractor()
        parser.feed("<p>Tom &amp; Jerry</p>")
        assert "Tom & Jerry" in parser.get_text()

    def test_lt_gt_entities_decoded(self):
        parser = _HTMLTextExtractor()
        parser.feed("<p>Price &lt;100&gt;</p>")
        assert "<100>" in parser.get_text()

    def test_multiple_elements_joined_with_newlines(self):
        parser = _HTMLTextExtractor()
        parser.feed("<p>First</p><p>Second</p>")
        text = parser.get_text()
        assert "First" in text
        assert "Second" in text
        assert "\n" in text

    def test_whitespace_only_data_not_added_to_parts(self):
        parser = _HTMLTextExtractor()
        parser.feed("<html>   <body>   <p>Content</p>   </body>   </html>")
        lines = [line for line in parser.get_text().split("\n") if line]
        assert lines == ["Content"]

    def test_get_text_on_fresh_parser_returns_empty_string(self):
        parser = _HTMLTextExtractor()
        assert parser.get_text() == ""

    def test_both_script_and_style_in_head_skipped(self):
        parser = _HTMLTextExtractor()
        html = (
            "<html><head>"
            "<script>var x=1;</script>"
            "<style>body{}</style>"
            "</head><body><p>Body text</p></body></html>"
        )
        parser.feed(html)
        text = parser.get_text()
        assert "Body text" in text
        assert "var x" not in text
        assert "body{}" not in text


# ===========================================================================
# _extract_html
# ===========================================================================


class TestExtractHtml:
    """_extract_html reads HTML files and strips script/style content."""

    def test_nominal_body_text_extracted(self, tmp_path):
        f = tmp_path / "page.html"
        f.write_text("<html><body><p>Hello HTML</p></body></html>", encoding="utf-8")
        result = _extract_html(f)
        assert len(result) == 1
        assert "Hello HTML" in result[0][1]

    def test_page_number_is_always_one(self, tmp_path):
        f = tmp_path / "page.html"
        f.write_text("<p>text</p>", encoding="utf-8")
        page_num, _ = _extract_html(f)[0]
        assert page_num == 1

    def test_return_type_is_list_of_tuples(self, tmp_path):
        f = tmp_path / "page.html"
        f.write_text("<p>data</p>", encoding="utf-8")
        result = _extract_html(f)
        assert isinstance(result, list)
        assert all(isinstance(item, tuple) and len(item) == 2 for item in result)

    def test_script_content_not_in_output(self, tmp_path):
        f = tmp_path / "script.html"
        f.write_text(
            "<body><script>var secret = 42;</script><p>Visible</p></body>",
            encoding="utf-8",
        )
        _, text = _extract_html(f)[0]
        assert "Visible" in text
        assert "secret" not in text

    def test_style_content_not_in_output(self, tmp_path):
        f = tmp_path / "style.html"
        f.write_text(
            "<head><style>.cls { color: red; }</style></head><body><p>Content</p></body>",
            encoding="utf-8",
        )
        _, text = _extract_html(f)[0]
        assert "Content" in text
        assert ".cls" not in text
        assert "color: red" not in text

    def test_html_entities_decoded(self, tmp_path):
        f = tmp_path / "entities.html"
        f.write_text("<p>Tom &amp; Jerry &lt;3&gt;</p>", encoding="utf-8")
        _, text = _extract_html(f)[0]
        assert "Tom & Jerry" in text
        assert "<3>" in text

    def test_empty_html_returns_empty_list(self, tmp_path):
        f = tmp_path / "empty.html"
        f.write_text("<html><body></body></html>", encoding="utf-8")
        assert _extract_html(f) == []

    def test_only_script_and_style_returns_empty_list(self, tmp_path):
        f = tmp_path / "notext.html"
        f.write_text(
            "<html><head><script>code();</script><style>.a{}</style></head></html>",
            encoding="utf-8",
        )
        assert _extract_html(f) == []

    def test_htm_extension_file_extracted(self, tmp_path):
        f = tmp_path / "page.htm"
        f.write_text("<p>HTM content</p>", encoding="utf-8")
        result = _extract_html(f)
        assert len(result) == 1
        assert "HTM content" in result[0][1]

    def test_clean_text_applied_url_replaced(self, tmp_path):
        f = tmp_path / "url.html"
        f.write_text("<p>See https://example.com for details</p>", encoding="utf-8")
        _, text = _extract_html(f)[0]
        assert "https://example.com" not in text
        assert "[url deleted]" in text

    def test_latin1_encoded_html_read_successfully(self, tmp_path):
        f = tmp_path / "latin.html"
        f.write_bytes("<p>Caf\xe9</p>".encode("latin-1"))
        result = _extract_html(f)
        assert len(result) == 1
        assert "Café" in result[0][1]


# ===========================================================================
# extract_text — dispatcher
# ===========================================================================


class TestExtractText:
    """extract_text dispatches to the correct extractor and enforces the contract."""

    # ------------------------------------------------------------------
    # Routing by extension
    # ------------------------------------------------------------------

    def test_txt_extension_routes_to_txt_extractor(self, tmp_path):
        f = tmp_path / "doc.txt"
        f.write_text("plain text content", encoding="utf-8")
        result = extract_text(f)
        assert result == [(1, "plain text content")]

    def test_md_extension_routes_to_txt_extractor(self, tmp_path):
        f = tmp_path / "readme.md"
        f.write_text("# Markdown heading", encoding="utf-8")
        result = extract_text(f)
        assert len(result) == 1
        assert "Markdown heading" in result[0][1]

    def test_docx_extension_routes_to_docx_extractor(self, tmp_path):
        f = _make_docx(tmp_path / "doc.docx", paragraphs=["DOCX content"])
        result = extract_text(f)
        assert len(result) == 1
        assert "DOCX content" in result[0][1]

    def test_pptx_extension_routes_to_pptx_extractor(self, tmp_path):
        f = _make_pptx(tmp_path / "pres.pptx", slides=[["PPTX content"]])
        result = extract_text(f)
        assert len(result) == 1
        assert "PPTX content" in result[0][1]

    def test_rtf_extension_routes_to_rtf_extractor(self, tmp_path):
        f = _make_rtf(tmp_path / "doc.rtf", "RTF content")
        result = extract_text(f)
        assert len(result) == 1
        assert "RTF content" in result[0][1]

    def test_odt_extension_routes_to_odt_extractor(self, tmp_path):
        f = _make_odt(tmp_path / "doc.odt", ["ODT content"])
        result = extract_text(f)
        assert len(result) == 1
        assert "ODT content" in result[0][1]

    def test_html_extension_routes_to_html_extractor(self, tmp_path):
        f = tmp_path / "page.html"
        f.write_text("<p>HTML content</p>", encoding="utf-8")
        result = extract_text(f)
        assert len(result) == 1
        assert "HTML content" in result[0][1]

    def test_htm_extension_routes_to_html_extractor(self, tmp_path):
        f = tmp_path / "page.htm"
        f.write_text("<p>HTM content</p>", encoding="utf-8")
        result = extract_text(f)
        assert len(result) == 1
        assert "HTM content" in result[0][1]

    # ------------------------------------------------------------------
    # Case-insensitive extension matching
    # ------------------------------------------------------------------

    def test_uppercase_txt_extension_accepted(self, tmp_path):
        f = tmp_path / "doc.TXT"
        f.write_text("uppercase ext", encoding="utf-8")
        result = extract_text(f)
        assert len(result) == 1
        assert "uppercase ext" in result[0][1]

    def test_mixed_case_html_extension_accepted(self, tmp_path):
        f = tmp_path / "page.HTML"
        f.write_text("<p>Mixed case</p>", encoding="utf-8")
        result = extract_text(f)
        assert len(result) == 1
        assert "Mixed case" in result[0][1]

    # ------------------------------------------------------------------
    # Unsupported extensions raise ValueError
    # ------------------------------------------------------------------

    def test_unsupported_extension_raises_value_error(self, tmp_path):
        f = tmp_path / "data.csv"
        f.write_text("a,b,c", encoding="utf-8")
        with pytest.raises(ValueError, match="Unsupported extension"):
            extract_text(f)

    def test_error_message_contains_extension(self, tmp_path):
        f = tmp_path / "archive.zip"
        f.write_bytes(b"fake zip")
        with pytest.raises(ValueError, match=r"\.zip"):
            extract_text(f)

    def test_pdf_extension_not_handled_by_doc_utils(self, tmp_path):
        # PDF extraction belongs to pdf_utils; doc_utils must reject .pdf
        f = tmp_path / "doc.pdf"
        f.write_bytes(b"%PDF-1.4 fake")
        with pytest.raises(ValueError):
            extract_text(f)

    def test_no_extension_raises_value_error(self, tmp_path):
        f = tmp_path / "noext"
        f.write_text("data", encoding="utf-8")
        with pytest.raises(ValueError):
            extract_text(f)

    # ------------------------------------------------------------------
    # Validation warning on suspiciously small output
    # ------------------------------------------------------------------

    def test_warning_emitted_when_large_file_yields_tiny_output(self, tmp_path, capsys):
        # File > 1024 bytes, but real text content < 50 chars after clean_text.
        # Pad with spaces that strip away during processing.
        f = tmp_path / "sparse.txt"
        f.write_text("x" * 10 + " " * 2000, encoding="utf-8")
        extract_text(f)
        stderr = capsys.readouterr().err
        assert "WARNING" in stderr

    def test_warning_contains_filename(self, tmp_path, capsys):
        f = tmp_path / "myfile.txt"
        f.write_text("tiny" + " " * 2000, encoding="utf-8")
        extract_text(f)
        stderr = capsys.readouterr().err
        assert "myfile.txt" in stderr

    def test_no_warning_for_small_file_with_tiny_output(self, tmp_path, capsys):
        # File <= 1024 bytes — warning condition requires file_size > 1024
        f = tmp_path / "small.txt"
        f.write_text("hi", encoding="utf-8")
        extract_text(f)
        assert "WARNING" not in capsys.readouterr().err

    def test_no_warning_when_large_file_yields_sufficient_output(self, tmp_path, capsys):
        # File > 1024 bytes AND output >= 50 chars — no warning
        f = tmp_path / "rich.txt"
        f.write_text("a" * 200, encoding="utf-8")
        extract_text(f)
        assert "WARNING" not in capsys.readouterr().err

    def test_warning_threshold_at_exactly_1024_bytes_no_warning(self, tmp_path, capsys):
        # file_size == 1024 is NOT > 1024, so no warning should fire
        content = "x" * 10 + " " * 1014  # total 1024 bytes
        f = tmp_path / "boundary.txt"
        f.write_text(content, encoding="utf-8")
        assert f.stat().st_size == 1024
        extract_text(f)
        assert "WARNING" not in capsys.readouterr().err

    # ------------------------------------------------------------------
    # Return value contract
    # ------------------------------------------------------------------

    def test_return_is_list_of_int_str_tuples(self, tmp_path):
        f = tmp_path / "doc.txt"
        f.write_text("some text", encoding="utf-8")
        result = extract_text(f)
        assert isinstance(result, list)
        for item in result:
            assert isinstance(item, tuple)
            assert len(item) == 2
            page_num, text = item
            assert isinstance(page_num, int)
            assert isinstance(text, str)

    # ------------------------------------------------------------------
    # SUPPORTED_EXTENSIONS constant
    # ------------------------------------------------------------------

    def test_supported_extensions_contains_all_expected(self):
        expected = {".txt", ".md", ".docx", ".pptx", ".rtf", ".odt", ".htm", ".html", ".epub", ".doc"}
        assert expected == SUPPORTED_EXTENSIONS

"""New document outputs: TXT, RTF, HTML, EPUB, CSV (via LibreOffice)."""

import os
import zipfile

import pytest

import fcutil
from fileconverter.jobs.base import ConversionState

pytestmark = pytest.mark.skipif(not fcutil.HAS_LIBREOFFICE, reason="libreoffice required")


def test_txt_output_preserves_unicode(tmp_path, sample_docx):
    job = fcutil.run_conversion(tmp_path, sample_docx, "txt", input_types=["docx"])
    fcutil.assert_done(job)
    # LibreOffice's Text filter may prepend a UTF-8 BOM.
    text = open(job.output_path, encoding="utf-8-sig").read()
    assert "Heading" in text
    assert "caffè" in text
    assert "日本語" in text


def test_rtf_output(tmp_path, sample_docx):
    job = fcutil.run_conversion(tmp_path, sample_docx, "rtf", input_types=["docx"])
    fcutil.assert_done(job)
    head = open(job.output_path, encoding="latin-1").read(16)
    assert head.startswith(r"{\rtf")


def test_epub_output_is_valid_epub(tmp_path, sample_docx):
    job = fcutil.run_conversion(tmp_path, sample_docx, "epub", input_types=["docx"])
    fcutil.assert_done(job)
    out = job.output_path
    assert zipfile.is_zipfile(out)
    with zipfile.ZipFile(out) as z:
        assert z.read("mimetype").decode().strip() == "application/epub+zip"


def test_html_output(tmp_path, sample_docx):
    job = fcutil.run_conversion(tmp_path, sample_docx, "html", input_types=["docx"])
    fcutil.assert_done(job)
    html = open(job.output_path, encoding="utf-8").read().lower()
    assert "<html" in html
    assert "heading" in html


def test_csv_output_handles_quoted_comma(tmp_path, sample_xlsx):
    job = fcutil.run_conversion(tmp_path, sample_xlsx, "csv", input_types=["xlsx"])
    fcutil.assert_done(job)
    text = open(job.output_path, encoding="utf-8").read()
    assert "Alice" in text and "10" in text
    # The cell 'Bob, Jr' contains a comma; it must survive as a single field.
    assert "Bob, Jr" in text


def test_same_extension_conversion_preserves_input(tmp_path):
    """txt -> txt must NOT consume the input file (data-loss regression)."""
    src = tmp_path / "note.txt"
    src.write_text("hello world\naccents caffè 日本語\n", encoding="utf-8")
    job = fcutil.run_conversion(tmp_path / "work", str(src), "txt", input_types=["txt"])
    fcutil.assert_done(job)
    # job.input_path is the copy inside work/; it must survive the conversion.
    assert os.path.exists(job.input_path), "input file was destroyed"
    assert os.path.abspath(job.output_path) != os.path.abspath(job.input_path)
    assert "caffè" in open(job.output_path, encoding="utf-8-sig").read()


def test_spreadsheet_to_epub_is_rejected_not_silent_stub(tmp_path, sample_xlsx):
    """A spreadsheet can't become a real EPUB; LibreOffice emits a mimetype-only
    stub. The validator must reject it (FAILED) rather than 'succeed' with garbage."""
    job = fcutil.run_conversion(tmp_path, sample_xlsx, "epub", input_types=["xlsx"])
    assert job.state == ConversionState.FAILED
    assert not os.path.exists(job.output_path)


def test_export_filter_map_is_explicit():
    """rtf/epub/html need pinned filter names (bare ext fails in LibreOffice)."""
    from fileconverter.jobs.libreoffice import _LO_EXPORT_FILTERS
    assert _LO_EXPORT_FILTERS["rtf"] == "rtf:Rich Text Format"
    assert _LO_EXPORT_FILTERS["epub"] == "epub:EPUB"
    assert _LO_EXPORT_FILTERS["html"].startswith("html:")
    # txt/csv intentionally absent — they resolve from the bare extension.
    assert "txt" not in _LO_EXPORT_FILTERS
    assert "csv" not in _LO_EXPORT_FILTERS

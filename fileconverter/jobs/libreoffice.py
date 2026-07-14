"""LibreOffice headless backend — replaces Office COM interop (Word/Excel/PowerPoint)."""

from __future__ import annotations
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile

from fileconverter.helpers import LIBREOFFICE_OUTPUTS
from fileconverter.i18n import _
from fileconverter.integration import install_hint
from fileconverter.jobs.base import ConversionJob
from fileconverter.jobs.imagemagick import ImageMagickJob
from fileconverter.jobs.proc import run_cancellable
from fileconverter.presets import ConversionPreset

# Explicit LibreOffice export filters. For docx/odt/xlsx/ods/pptx/odp/txt/csv,
# LibreOffice resolves the right filter from the bare extension. But rtf/epub/
# html need the filter named explicitly — with a bare extension LibreOffice
# reports "no export filter found" when the source isn't already that module's
# native type (e.g. html → rtf). Keys are output_type, values are the
# `--convert-to` argument.
_LO_EXPORT_FILTERS = {
    "rtf": "rtf:Rich Text Format",
    "epub": "epub:EPUB",
    "html": "html:HTML (StarWriter)",
}


class LibreOfficeJob(ConversionJob):
    def __init__(self, preset: ConversionPreset, input_path: str):
        super().__init__(preset, input_path)

    @staticmethod
    def _profile_args(tmpdir: str) -> list[str]:
        """Give this invocation its own LibreOffice user profile.

        Two `soffice --headless` processes sharing the default profile do not
        both convert: the second one hands its request to the first instance
        and exits 0 having produced nothing. With max_simultaneous_conversions
        > 1 (the default is 2), a batch of documents silently lost half its
        outputs — the jobs reported success with no file on disk. A private
        profile per invocation makes them fully independent.
        """
        profile = os.path.join(tmpdir, "loprofile")
        return [f"-env:UserInstallation=file://{profile}"]

    @staticmethod
    def _find_libreoffice() -> str:
        for cmd in ("libreoffice", "soffice"):
            path = shutil.which(cmd)
            if path:
                return path
        if sys.platform == "darwin":
            # LibreOffice.app isn't on PATH; look inside the app bundle.
            for p in (
                "/Applications/LibreOffice.app/Contents/MacOS/soffice",
                os.path.expanduser("~/Applications/LibreOffice.app/Contents/MacOS/soffice"),
            ):
                if os.path.exists(p) and os.access(p, os.X_OK):
                    return p
        raise FileNotFoundError(
            f"LibreOffice not found. {install_hint('libreoffice')}"
        )

    def _convert(self) -> None:
        lo = self._find_libreoffice()
        out_type = self.preset.output_type

        if out_type == "pdf":
            self._convert_to_pdf(lo)
        elif out_type in LIBREOFFICE_OUTPUTS:
            self._convert_direct(lo, out_type)
        else:
            # Two-step: document → PDF → target image format
            self._convert_via_pdf(lo)

    def _convert_direct(self, lo: str, out_type: str) -> None:
        """Direct office-format conversion via `--convert-to`.

        Converts into a temporary directory, then moves the result to the final
        output path. This is essential for same-extension conversions (e.g.
        txt->txt): LibreOffice names its output after the input basename, so
        converting straight into the input's own directory would overwrite the
        original file — and the subsequent move would then relocate it, silently
        destroying the user's input.

        Uses an explicit filter for formats LibreOffice can't resolve from the
        bare extension (rtf/epub/html), and verifies a non-degenerate file was
        actually produced (LibreOffice can exit 0 with no — or stub — output).
        """
        self.user_state = _("Converting document...")
        self.progress = 0.1

        convert_to = _LO_EXPORT_FILTERS.get(out_type, out_type)
        with tempfile.TemporaryDirectory(prefix="fileconverter-") as tmpdir:
            result = run_cancellable(
                [lo] + self._profile_args(tmpdir)
                + ["--headless", "--convert-to", convert_to, "--outdir", tmpdir,
                   self.input_path], self, timeout=600,
            )
            produced = os.path.join(
                tmpdir,
                os.path.splitext(os.path.basename(self.input_path))[0] + "." + out_type,
            )
            if result.returncode != 0:
                raise RuntimeError(f"LibreOffice error: {result.stderr}")
            if not os.path.exists(produced) or os.path.getsize(produced) == 0:
                raise RuntimeError(
                    f"LibreOffice produced no output for '{out_type}'. "
                    f"{result.stdout.strip()} {result.stderr.strip()}".strip()
                )
            self._validate_output(out_type, produced)
            shutil.move(produced, self.output_path)

        self.progress = 1.0

    @staticmethod
    def _validate_output(out_type: str, path: str) -> None:
        """Reject the structurally-degenerate output LibreOffice emits for some
        incompatible source/target pairs — e.g. a spreadsheet exported to EPUB
        yields a mimetype-only stub zip that exits 0 but isn't a usable book."""
        if out_type == "epub":
            try:
                with zipfile.ZipFile(path) as z:
                    names = set(z.namelist())
            except zipfile.BadZipFile:
                raise RuntimeError("LibreOffice produced an invalid EPUB (not a zip).")
            if "META-INF/container.xml" not in names:
                raise RuntimeError(
                    "LibreOffice produced an incomplete EPUB (no META-INF/container.xml) — "
                    "the source document type may not be convertible to EPUB."
                )

    def _convert_to_pdf(self, lo: str) -> None:
        """Direct conversion to PDF.

        Converts into a temp dir (like _convert_direct) rather than straight
        into the input's folder: LibreOffice names its output after the input
        basename, so a pdf → pdf conversion would otherwise overwrite the
        source. The produced file is verified — LibreOffice can exit 0 having
        written nothing at all.
        """
        self.user_state = _("Converting document...")
        self.progress = 0.1

        with tempfile.TemporaryDirectory(prefix="fileconverter-") as tmpdir:
            result = run_cancellable(
                [lo] + self._profile_args(tmpdir)
                + ["--headless", "--convert-to", "pdf", "--outdir", tmpdir,
                   self.input_path], self, timeout=600,
            )
            if result.returncode != 0:
                raise RuntimeError(f"LibreOffice error: {result.stderr}")

            produced = os.path.join(
                tmpdir,
                os.path.splitext(os.path.basename(self.input_path))[0] + ".pdf",
            )
            if not os.path.exists(produced) or os.path.getsize(produced) == 0:
                raise RuntimeError(
                    "LibreOffice produced no PDF. "
                    f"{result.stdout.strip()} {result.stderr.strip()}".strip()
                )
            shutil.move(produced, self.output_path)

        self.progress = 1.0

    def _convert_via_pdf(self, lo: str) -> None:
        """Convert document to PDF first, then to target image format."""
        with tempfile.TemporaryDirectory(prefix="fileconverter-") as tmpdir:
            # Step 1: Document → PDF
            self.user_state = _("Exporting to PDF...")
            self.progress = 0.1

            result = run_cancellable(
                [lo] + self._profile_args(tmpdir)
                + ["--headless", "--convert-to", "pdf", "--outdir", tmpdir,
                   self.input_path], self, timeout=600,
            )
            if result.returncode != 0:
                raise RuntimeError(f"LibreOffice error: {result.stderr}")

            tmp_pdf = os.path.join(
                tmpdir,
                os.path.splitext(os.path.basename(self.input_path))[0] + ".pdf",
            )
            if not os.path.exists(tmp_pdf) or os.path.getsize(tmp_pdf) == 0:
                raise RuntimeError("LibreOffice did not produce expected PDF output")

            self.progress = 0.4

            # Step 2: PDF → target format via ImageMagick
            self.user_state = _("Converting to image...")
            img_job = ImageMagickJob(self.preset, tmp_pdf)
            img_job.link_cancel(self)
            img_job.output_paths = self.output_paths
            img_job._convert_cmd = ImageMagickJob._find_convert()
            img_job._is_pdf_input = True
            img_job._convert()

            self.progress = 1.0

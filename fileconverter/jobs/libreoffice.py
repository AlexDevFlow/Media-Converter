"""LibreOffice headless backend — replaces Office COM interop (Word/Excel/PowerPoint)."""

from __future__ import annotations
import os
import shutil
import subprocess
import tempfile

from fileconverter.i18n import _
from fileconverter.integration.install import install_hint
from fileconverter.jobs.base import ConversionJob
from fileconverter.jobs.imagemagick import ImageMagickJob
from fileconverter.presets import ConversionPreset


class LibreOfficeJob(ConversionJob):
    def __init__(self, preset: ConversionPreset, input_path: str):
        super().__init__(preset, input_path)

    @staticmethod
    def _find_libreoffice() -> str:
        for cmd in ("libreoffice", "soffice"):
            path = shutil.which(cmd)
            if path:
                return path
        raise FileNotFoundError(
            f"LibreOffice not found. {install_hint('libreoffice')}"
        )

    def _convert(self) -> None:
        lo = self._find_libreoffice()
        out_type = self.preset.output_type

        if out_type == "pdf":
            self._convert_to_pdf(lo)
        else:
            # Two-step: document → PDF → target image format
            self._convert_via_pdf(lo)

    def _convert_to_pdf(self, lo: str) -> None:
        """Direct conversion to PDF."""
        self.user_state = _("Converting document...")
        self.progress = 0.1

        out_dir = os.path.dirname(self.output_path)
        result = subprocess.run(
            [lo, "--headless", "--convert-to", "pdf", "--outdir", out_dir, self.input_path],
            capture_output=True, text=True, timeout=600,
        )
        if result.returncode != 0:
            raise RuntimeError(f"LibreOffice error: {result.stderr}")

        # LibreOffice names the output based on the input filename
        expected = os.path.join(
            out_dir,
            os.path.splitext(os.path.basename(self.input_path))[0] + ".pdf",
        )
        if expected != self.output_path and os.path.exists(expected):
            shutil.move(expected, self.output_path)

        self.progress = 1.0

    def _convert_via_pdf(self, lo: str) -> None:
        """Convert document to PDF first, then to target image format."""
        with tempfile.TemporaryDirectory(prefix="fileconverter-") as tmpdir:
            # Step 1: Document → PDF
            self.user_state = _("Exporting to PDF...")
            self.progress = 0.1

            result = subprocess.run(
                [lo, "--headless", "--convert-to", "pdf", "--outdir", tmpdir, self.input_path],
                capture_output=True, text=True, timeout=600,
            )
            if result.returncode != 0:
                raise RuntimeError(f"LibreOffice error: {result.stderr}")

            tmp_pdf = os.path.join(
                tmpdir,
                os.path.splitext(os.path.basename(self.input_path))[0] + ".pdf",
            )
            if not os.path.exists(tmp_pdf):
                raise RuntimeError("LibreOffice did not produce expected PDF output")

            self.progress = 0.4

            # Step 2: PDF → target format via ImageMagick
            self.user_state = _("Converting to image...")
            img_job = ImageMagickJob(self.preset, tmp_pdf)
            img_job.output_paths = self.output_paths
            img_job._convert_cmd = ImageMagickJob._find_convert()
            img_job._is_pdf_input = True
            img_job._convert()

            self.progress = 1.0

"""ImageMagick conversion backend — ported from ConversionJob_ImageMagick.cs."""

from __future__ import annotations
import os
import shutil
import subprocess

from fileconverter.i18n import _
from fileconverter.integration.install import install_hint
from fileconverter.jobs.base import ConversionJob
from fileconverter.presets import ConversionPreset

BASE_DPI_FOR_PDF = 200


class ImageMagickJob(ConversionJob):
    def __init__(self, preset: ConversionPreset, input_path: str):
        super().__init__(preset, input_path)
        self._is_pdf_input = False
        self._convert_cmd = ""

    @staticmethod
    def _find_convert() -> str:
        # ImageMagick 7 uses 'magick', ImageMagick 6 uses 'convert' or 'convert-im6'
        for cmd in ("magick", "convert", "convert-im6", "convert-im6.q16",
                     "convert-im6.q16hdri"):
            path = shutil.which(cmd)
            if path:
                return path
        raise FileNotFoundError(
            f"ImageMagick not found. {install_hint('imagemagick')}"
        )

    def _initialize(self) -> None:
        self._is_pdf_input = self.input_path.lower().endswith(".pdf")
        self._convert_cmd = self._find_convert()

    def _get_output_files_count(self) -> int:
        if not self.input_path.lower().endswith(".pdf"):
            return 1
        # Count PDF pages using ImageMagick identify
        try:
            cmd_name = self._find_convert()
            identify = cmd_name.replace("convert", "identify").replace("magick", "magick identify") if "magick" not in cmd_name else cmd_name
            if "magick" in cmd_name:
                result = subprocess.run(
                    [cmd_name, "identify", self.input_path],
                    capture_output=True, text=True, timeout=30,
                )
            else:
                identify_cmd = shutil.which("identify") or "identify"
                result = subprocess.run(
                    [identify_cmd, self.input_path],
                    capture_output=True, text=True, timeout=30,
                )
            return max(1, result.stdout.count("\n"))
        except Exception:
            return 1

    def _convert(self) -> None:
        if self._is_pdf_input:
            self._convert_pdf()
        else:
            self._convert_image(self.input_path, self.output_path)

    def _convert_pdf(self) -> None:
        """Convert each PDF page to an image."""
        scale = self.preset.get_setting_float("image_scale", 1.0)
        dpi = int(BASE_DPI_FOR_PDF * scale) if abs(scale - 1.0) >= 0.005 else BASE_DPI_FOR_PDF

        num_pages = len(self.output_paths)
        for i, out_path in enumerate(self.output_paths):
            if self.cancel_requested:
                return
            self.user_state = _("Page {current}/{total}").format(current=i + 1, total=num_pages)
            self.progress = i / num_pages

            args = [self._convert_cmd]
            if self._convert_cmd.endswith("magick"):
                args.append("convert")
            args += ["-density", str(dpi), f"{self.input_path}[{i}]"]
            args += self._quality_args()
            args += [out_path]

            result = subprocess.run(args, capture_output=True, text=True, timeout=300)
            if result.returncode != 0:
                raise RuntimeError(f"ImageMagick error: {result.stderr}")

            self.current_output_index = i

    def _convert_image(self, input_path: str, output_path: str) -> None:
        """Convert a single image file."""
        args = [self._convert_cmd]
        if self._convert_cmd.endswith("magick"):
            args.append("convert")
        args += [input_path]

        # Scale
        scale = self.preset.get_setting_float("image_scale", 1.0)
        if abs(scale - 1.0) >= 0.005:
            pct = f"{scale * 100:.1f}%"
            args += ["-resize", pct]

        # Rotation
        rotation = self.preset.get_setting_float("image_rotation", 0)
        if abs(rotation) >= 0.05:
            args += ["-rotate", str(rotation)]

        # Quality and format-specific args
        args += self._quality_args()
        args += [output_path]

        result = subprocess.run(args, capture_output=True, text=True, timeout=300)
        if result.returncode != 0:
            raise RuntimeError(f"ImageMagick error: {result.stderr}")

    def _quality_args(self) -> list[str]:
        out = self.preset.output_type
        if out in ("jpg", "webp", "avif"):
            q = self.preset.get_setting_int("image_quality", 85)
            return ["-quality", str(q)]
        elif out == "png":
            return ["-quality", "95"]
        elif out == "pdf":
            return ["-density", str(BASE_DPI_FOR_PDF)]
        return []

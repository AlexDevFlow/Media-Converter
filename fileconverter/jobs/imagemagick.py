"""ImageMagick conversion backend — ported from ConversionJob_ImageMagick.cs."""

from __future__ import annotations
import os
import shutil
import subprocess
import tempfile

from fileconverter.i18n import _
from fileconverter.integration import install_hint
from fileconverter.jobs.base import ConversionJob
from fileconverter.jobs.proc import run_cancellable, system_env
from fileconverter.presets import ConversionPreset

BASE_DPI_FOR_PDF = 200

# What `identify -format %m` should report per output type. ImageMagick
# builds missing a write delegate can exit 0 while silently writing the
# *input* format under the requested extension — validate instead of trusting.
_EXPECTED_FORMAT = {
    "avif": "AVIF", "bmp": "BMP", "jp2": "JP2", "jpg": "JPEG", "png": "PNG",
    "tga": "TGA", "tiff": "TIFF", "webp": "WEBP", "pdf": "PDF",
}

_write_formats_cache = None


def magick_write_formats() -> set:
    """Formats the local ImageMagick can encode (from `magick -list format`).

    Cached per process. Empty set when ImageMagick is missing entirely.
    """
    global _write_formats_cache
    if _write_formats_cache is None:
        formats = set()
        try:
            cmd = ImageMagickJob._find_convert()
            args = [cmd, "-list", "format"] if cmd.endswith("magick") \
                else [cmd.replace("convert", "identify"), "-list", "format"]
            out = subprocess.run(args, capture_output=True, text=True,
                                 timeout=30, env=system_env()).stdout
            for line in out.splitlines():
                #      "     JP2* JP2       rw-   JPEG-2000 ..." — mode has
                # r=read, w=write; strip the native-blob marker '*'.
                parts = line.split()
                if len(parts) >= 3 and "w" in parts[2] and parts[2][0] in "rw-":
                    formats.add(parts[0].rstrip("*"))
        except (FileNotFoundError, subprocess.SubprocessError, OSError):
            pass
        _write_formats_cache = formats
    return _write_formats_cache


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
                    capture_output=True, text=True, timeout=30, env=system_env(),
                )
            else:
                identify_cmd = shutil.which("identify") or "identify"
                result = subprocess.run(
                    [identify_cmd, self.input_path],
                    capture_output=True, text=True, timeout=30, env=system_env(),
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

        # Builds without the OpenJPEG delegate can't write JP2 (and would
        # silently keep another format) — rasterise the page to PNG, then wrap
        # it with ffmpeg's native JPEG-2000 encoder instead.
        jp2_via_ffmpeg = (self.preset.output_type == "jp2"
                          and "JP2" not in magick_write_formats())

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

            if jp2_via_ffmpeg:
                with tempfile.TemporaryDirectory(prefix="fileconverter-") as tmpdir:
                    tmp_png = os.path.join(tmpdir, f"page-{i}.png")
                    result = run_cancellable(args + [tmp_png], self, timeout=300)
                    if result.returncode != 0:
                        raise RuntimeError(f"ImageMagick error: {result.stderr}")
                    self._png_to_jp2(tmp_png, out_path)
            else:
                args += self._quality_args()
                args += [out_path]
                result = run_cancellable(args, self, timeout=300)
                if result.returncode != 0:
                    raise RuntimeError(f"ImageMagick error: {result.stderr}")

            self.current_output_index = i

    def _png_to_jp2(self, png_path: str, out_path: str) -> None:
        from fileconverter.jobs.ffmpeg import FFmpegJob, jp2_quality_to_qv
        ffmpeg = FFmpegJob._find_ffmpeg()
        quality = self.preset.get_setting_int("image_quality", 85)
        result = run_cancellable(
            [ffmpeg, "-y", "-i", png_path, "-c:v", "jpeg2000", "-format", "jp2",
             "-q:v", str(jp2_quality_to_qv(quality)), out_path], self, timeout=300)
        if result.returncode != 0:
            raise RuntimeError(f"ffmpeg error (JP2): {result.stderr[-400:]}")

    def _convert_image(self, input_path: str, output_path: str) -> None:
        """Convert a single image file."""
        args = [self._convert_cmd]
        if self._convert_cmd.endswith("magick"):
            args.append("convert")

        # Animated inputs (gif) to a still format would otherwise explode into
        # out-0.png, out-1.png, ... and leave the expected output path empty —
        # take the first frame instead.
        in_ext = os.path.splitext(input_path)[1].lower().lstrip(".")
        out_ext = os.path.splitext(output_path)[1].lower().lstrip(".")
        if in_ext == "gif" and out_ext not in ("gif", "webp", "avif"):
            args += [f"{input_path}[0]"]
        else:
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

        result = run_cancellable(args, self, timeout=300)
        if result.returncode != 0:
            raise RuntimeError(f"ImageMagick error: {result.stderr}")
        self._validate_output_format(output_path)

    def _validate_output_format(self, output_path: str) -> None:
        """Reject outputs whose actual format doesn't match the extension —
        a build without the needed write delegate exits 0 but keeps the input
        format (e.g. PNG bytes in a .jp2 file)."""
        expected = _EXPECTED_FORMAT.get(self.preset.output_type)
        if not expected:
            return
        try:
            args = [self._convert_cmd]
            if self._convert_cmd.endswith("magick"):
                args.append("identify")
            else:
                args = [self._convert_cmd.replace("convert", "identify")]
            out = subprocess.run(args + ["-format", "%m\n", output_path],
                                 capture_output=True, text=True, timeout=60,
                                 env=system_env())
            actual = out.stdout.strip().splitlines()[0] if out.stdout.strip() else ""
        except (subprocess.SubprocessError, OSError, IndexError):
            return  # can't verify — don't fail a conversion that may be fine
        if actual and actual != expected:
            raise RuntimeError(
                f"ImageMagick wrote {actual} data instead of {expected} — this "
                f"build lacks the {expected} write delegate. "
                f"{install_hint('imagemagick')}"
            )

    def _quality_args(self) -> list[str]:
        out = self.preset.output_type
        if out in ("jpg", "webp", "avif", "jp2"):
            q = self.preset.get_setting_int("image_quality", 85)
            return ["-quality", str(q)]
        elif out == "png":
            return ["-quality", "95"]
        elif out == "tiff":
            # LZW is broadly supported and lossless; smaller than uncompressed.
            return ["-compress", "LZW"]
        elif out == "bmp":
            return []
        elif out == "pdf":
            return ["-density", str(BASE_DPI_FOR_PDF)]
        return []

"""Conversion job factory — ported from ConversionJobFactory.cs."""

from __future__ import annotations
import os

from fileconverter.helpers import LIBREOFFICE_OUTPUTS, OFFICE_EXTENSIONS
from fileconverter.presets import ConversionPreset
from fileconverter.jobs.base import ConversionJob

# Output types handled by ImageMagick (raster image outputs + pdf rasterisation).
_IMAGEMAGICK_OUTPUTS = {"avif", "bmp", "jpg", "png", "tiff", "webp", "pdf"}


def create_job(preset: ConversionPreset, input_path: str, hw_accel: str = "off") -> ConversionJob:
    """Route to the correct conversion backend based on input extension and output type.

    Args:
        preset: The conversion preset to use.
        input_path: Path to the input file.
        hw_accel: Resolved hardware acceleration mode ("off", "nvenc", "vaapi").
    """
    from fileconverter.jobs.ffmpeg import FFmpegJob
    from fileconverter.jobs.imagemagick import ImageMagickJob
    from fileconverter.jobs.libreoffice import LibreOfficeJob
    from fileconverter.jobs.gif import GifJob

    ext = os.path.splitext(input_path)[1].lower().lstrip(".")
    out_type = preset.output_type

    # Office document outputs always use LibreOffice (regardless of input).
    if out_type in LIBREOFFICE_OUTPUTS:
        return LibreOfficeJob(preset, input_path)

    # Office document inputs go through LibreOffice (which may chain to ImageMagick for raster outputs).
    if ext in OFFICE_EXTENSIONS:
        return LibreOfficeJob(preset, input_path)

    # GIF output → special two-pass pipeline
    if out_type == "gif":
        return GifJob(preset, input_path)

    # ICO output → FFmpeg (no hw accel; tiny output)
    if out_type == "ico":
        return FFmpegJob(preset, input_path, hw_accel="off")

    # Raster image outputs → ImageMagick
    if out_type in _IMAGEMAGICK_OUTPUTS:
        return ImageMagickJob(preset, input_path)

    # Video outputs (mp4, mkv, mov) get hardware acceleration.
    # Audio-only outputs and other video containers don't.
    effective_hw = hw_accel if out_type in ("mp4", "mkv", "mov") else "off"
    return FFmpegJob(preset, input_path, hw_accel=effective_hw)

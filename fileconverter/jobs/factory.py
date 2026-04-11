"""Conversion job factory — ported from ConversionJobFactory.cs."""

from __future__ import annotations
import os

from fileconverter.helpers import OFFICE_EXTENSIONS
from fileconverter.presets import ConversionPreset
from fileconverter.jobs.base import ConversionJob


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

    # Office documents → LibreOffice
    if ext in OFFICE_EXTENSIONS:
        return LibreOfficeJob(preset, input_path)

    # GIF output → special two-pass pipeline
    if preset.output_type == "gif":
        return GifJob(preset, input_path)

    # ICO output → ImageMagick resize then FFmpeg
    if preset.output_type == "ico":
        return FFmpegJob(preset, input_path, hw_accel="off")

    # Image outputs → ImageMagick
    if preset.output_type in ("avif", "jpg", "png", "webp", "pdf"):
        return ImageMagickJob(preset, input_path)

    # Video outputs (mp4, mkv) get hardware acceleration
    # Audio-only outputs don't benefit from GPU encoding
    effective_hw = hw_accel if preset.output_type in ("mp4", "mkv") else "off"
    return FFmpegJob(preset, input_path, hw_accel=effective_hw)

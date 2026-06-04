"""Shared test helpers: run real conversions and probe their output.

These are integration helpers — they drive the actual ffmpeg / LibreOffice /
ImageMagick backends and inspect the produced files with ffprobe / identify.
Everything degrades to skips when a tool is missing (see the HAS_* flags).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess

from fileconverter.jobs.base import ConversionState
from fileconverter.jobs.factory import create_job
from fileconverter.presets import ConversionPreset

# --- Tool availability -----------------------------------------------------

HAS_FFMPEG = shutil.which("ffmpeg") is not None
HAS_FFPROBE = shutil.which("ffprobe") is not None
HAS_LIBREOFFICE = (shutil.which("libreoffice") or shutil.which("soffice")) is not None
HAS_IMAGEMAGICK = (shutil.which("magick") or shutil.which("convert")) is not None
HAS_IDENTIFY = (shutil.which("identify") or shutil.which("magick")) is not None

_ENCODER_CACHE: dict[str, bool] = {}


def encoder_available(name: str) -> bool:
    """True if the local ffmpeg build exposes the given encoder."""
    if not HAS_FFMPEG:
        return False
    if name not in _ENCODER_CACHE:
        out = subprocess.run(["ffmpeg", "-hide_banner", "-encoders"],
                             capture_output=True, text=True)
        # encoder lines look like " V..... libx265   ...": match the token.
        present = any(line.split()[1:2] == [name]
                      for line in out.stdout.splitlines() if line.strip())
        _ENCODER_CACHE[name] = present
    return _ENCODER_CACHE[name]


# --- Running conversions ---------------------------------------------------

def run_conversion(work_dir, src, output_type, *, settings=None, input_types=None,
                   template="(p)(f)", hw_accel="off", post_action="none",
                   dest_name=None):
    """Copy `src` into `work_dir`, run a single conversion, return the job.

    The input is copied first so outputs land in the isolated work_dir and the
    original sample is never mutated. Returns the finished ConversionJob; check
    `.state` / `.error_message` / `.output_paths`.
    """
    os.makedirs(work_dir, exist_ok=True)
    dest_name = dest_name or os.path.basename(src)
    local_src = os.path.join(str(work_dir), dest_name)
    shutil.copy2(src, local_src)
    ext = os.path.splitext(local_src)[1].lstrip(".").lower()

    preset = ConversionPreset(
        name=f"Test To {output_type}",
        output_type=output_type,
        input_types=input_types or [ext],
        input_post_action=post_action,
        output_template=template,
        settings=dict(settings or {}),
    )
    job = create_job(preset, local_src, hw_accel=hw_accel)
    job.prepare()
    job.run()
    return job


def assert_done(job):
    """Assert the job finished successfully, with a useful message if not."""
    assert job.state == ConversionState.DONE, (
        f"conversion failed (state={job.state.value}): {job.error_message}"
    )
    for p in job.output_paths:
        assert os.path.exists(p), f"declared output missing: {p}"
        assert os.path.getsize(p) > 0, f"output is empty: {p}"
    return job


# --- ffprobe helpers -------------------------------------------------------

def ffprobe_json(path):
    out = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json",
         "-show_format", "-show_streams", str(path)],
        capture_output=True, text=True,
    )
    return json.loads(out.stdout or "{}")


def streams(path, codec_type=None):
    data = ffprobe_json(path).get("streams", [])
    if codec_type:
        return [s for s in data if s.get("codec_type") == codec_type]
    return data


def codec_name(path, codec_type):
    s = streams(path, codec_type)
    return s[0].get("codec_name") if s else None


def has_stream(path, codec_type):
    return bool(streams(path, codec_type))


def format_name(path):
    return ffprobe_json(path).get("format", {}).get("format_name", "")


def pix_fmt(path):
    s = streams(path, "video")
    return s[0].get("pix_fmt") if s else None


def video_dims(path):
    s = streams(path, "video")
    if not s:
        return None
    return int(s[0]["width"]), int(s[0]["height"])


def channels(path):
    s = streams(path, "audio")
    return int(s[0]["channels"]) if s and "channels" in s[0] else None


def has_codec_tag(path, tag):
    """True if the first video stream carries the given codec_tag_string."""
    s = streams(path, "video")
    return bool(s) and s[0].get("codec_tag_string") == tag


# --- ImageMagick identify helpers ------------------------------------------

def _identify(args):
    magick = shutil.which("identify")
    if magick:
        return subprocess.run([magick, *args], capture_output=True, text=True)
    return subprocess.run([shutil.which("magick"), "identify", *args],
                          capture_output=True, text=True)


def image_format(path):
    """Return the ImageMagick format code of the first frame, e.g. 'JP2'."""
    out = _identify(["-format", "%m\n", str(path)])
    return out.stdout.strip().splitlines()[0] if out.stdout.strip() else ""


def image_dims(path):
    out = _identify(["-format", "%w %h\n", str(path)])
    first = out.stdout.strip().splitlines()[0]
    w, h = first.split()
    return int(w), int(h)

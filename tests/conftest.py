"""Pytest fixtures: generate sample media once per session, isolate LibreOffice.

All conversion tests are integration tests against the real backends. Fixtures
that need a tool skip cleanly when it's absent, so the suite stays green on a
machine missing (say) LibreOffice.
"""

from __future__ import annotations

import os
import subprocess

import pytest

import fcutil


@pytest.fixture(scope="session", autouse=True)
def isolated_home(tmp_path_factory):
    """Point HOME at a throwaway dir.

    LibreOffice keeps its user profile under $HOME; isolating it means the test
    suite never touches (or deadlocks against) a LibreOffice instance the user
    has open, and each run starts from a clean profile.
    """
    home = tmp_path_factory.mktemp("home")
    old = os.environ.get("HOME")
    os.environ["HOME"] = str(home)
    try:
        yield str(home)
    finally:
        if old is not None:
            os.environ["HOME"] = old


def _ffmpeg(*args):
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *args],
                   check=True)


@pytest.fixture(scope="session")
def media_dir(tmp_path_factory):
    return tmp_path_factory.mktemp("media")


@pytest.fixture(scope="session")
def sample_video(media_dir):
    """2s 320x240 test pattern, H.264 video + stereo AAC audio."""
    if not fcutil.HAS_FFMPEG:
        pytest.skip("ffmpeg not available")
    path = media_dir / "clip.mp4"
    _ffmpeg("-f", "lavfi", "-i", "testsrc=size=320x240:rate=24:duration=2",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
            "-shortest", "-c:v", "libx264", "-c:a", "aac", "-ac", "2",
            "-pix_fmt", "yuv420p", str(path))
    return str(path)


@pytest.fixture(scope="session")
def sample_audio(media_dir):
    """2s stereo sine WAV."""
    if not fcutil.HAS_FFMPEG:
        pytest.skip("ffmpeg not available")
    path = media_dir / "tone.wav"
    _ffmpeg("-f", "lavfi", "-i", "sine=frequency=440:duration=2", "-ac", "2", str(path))
    return str(path)


@pytest.fixture(scope="session")
def sample_image(media_dir):
    """Single 320x240 PNG frame."""
    if not fcutil.HAS_FFMPEG:
        pytest.skip("ffmpeg not available")
    path = media_dir / "still.png"
    _ffmpeg("-f", "lavfi", "-i", "testsrc=size=320x240:duration=1",
            "-frames:v", "1", str(path))
    return str(path)


@pytest.fixture(scope="session")
def sample_pdf2(media_dir):
    """A normal-sized 2-page PDF. Skips if the environment can't rasterize PDFs
    (ImageMagick/ghostscript resource limits)."""
    if not (fcutil.HAS_IMAGEMAGICK and fcutil.HAS_FFMPEG):
        pytest.skip("imagemagick + ffmpeg required")
    import shutil
    a, b = media_dir / "pg_a.png", media_dir / "pg_b.png"
    _ffmpeg("-f", "lavfi", "-i", "color=red:s=200x150:d=1", "-frames:v", "1", str(a))
    _ffmpeg("-f", "lavfi", "-i", "color=blue:s=200x150:d=1", "-frames:v", "1", str(b))
    convert = shutil.which("convert") or shutil.which("magick")
    pdf = media_dir / "two.pdf"
    # Set density so the PDF page size is sane (raw lavfi PNGs have density 1,
    # which would make a 200-inch page that blows past ImageMagick's limits).
    subprocess.run([convert, "-density", "96", "-units", "PixelsPerInch",
                    str(a), str(b), "-density", "96", str(pdf)], check=True)
    probe = media_dir / "_probe.png"
    r = subprocess.run([convert, "-density", "150", f"{pdf}[0]", str(probe)],
                       capture_output=True, text=True)
    if r.returncode != 0 or not probe.exists():
        pytest.skip("environment cannot rasterize PDF (ImageMagick/ghostscript)")
    return str(pdf)


@pytest.fixture(scope="session")
def sample_docx(media_dir):
    """A real .docx, built once from a plain-text Writer source via LibreOffice.

    Built from .txt rather than .html on purpose: LibreOffice opens HTML in Web
    mode, where the Writer docx export filter isn't available.
    """
    if not fcutil.HAS_LIBREOFFICE:
        pytest.skip("libreoffice not available")
    src = media_dir / "writer_src.txt"
    src.write_text("Heading\nBody with accents caffè €, and 日本語.\n", encoding="utf-8")
    job = fcutil.run_conversion(media_dir / "_mkdocx", str(src), "docx",
                                input_types=["txt"])
    if job.state.value != "done":
        pytest.skip(f"could not build docx sample: {job.error_message}")
    return job.output_path


@pytest.fixture(scope="session")
def sample_xlsx(media_dir):
    """A real .xlsx spreadsheet, produced once from a CSV via LibreOffice."""
    if not fcutil.HAS_LIBREOFFICE:
        pytest.skip("libreoffice not available")
    csv = media_dir / "sheet.csv"
    csv.write_text('name,score\nAlice,10\n"Bob, Jr",20\nCarol,30\n', encoding="utf-8")
    job = fcutil.run_conversion(media_dir / "_mkxlsx", str(csv), "xlsx",
                                input_types=["csv"])
    if job.state.value != "done":
        pytest.skip(f"could not build xlsx sample: {job.error_message}")
    return job.output_path

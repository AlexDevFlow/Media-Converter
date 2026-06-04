"""New image outputs: JP2 (JPEG 2000), TGA (Truevision Targa)."""

import pytest

import fcutil

pytestmark = pytest.mark.skipif(
    not (fcutil.HAS_IMAGEMAGICK and fcutil.HAS_IDENTIFY),
    reason="imagemagick required",
)

IMG_IN = ["png", "jpg", "bmp", "webp", "gif", "tiff"]


def test_jp2_output(tmp_path, sample_image):
    job = fcutil.run_conversion(tmp_path, sample_image, "jp2",
                                settings={"image_quality": 85}, input_types=IMG_IN)
    fcutil.assert_done(job)
    assert fcutil.image_format(job.output_path) == "JP2"


def test_tga_output(tmp_path, sample_image):
    job = fcutil.run_conversion(tmp_path, sample_image, "tga", input_types=IMG_IN)
    fcutil.assert_done(job)
    assert fcutil.image_format(job.output_path) == "TGA"


def test_jp2_scale(tmp_path, sample_image):
    job = fcutil.run_conversion(tmp_path, sample_image, "jp2",
                                settings={"image_scale": 0.5}, input_types=IMG_IN)
    fcutil.assert_done(job)
    assert fcutil.image_dims(job.output_path) == (160, 120)


def test_tga_rotate_90(tmp_path, sample_image):
    job = fcutil.run_conversion(tmp_path, sample_image, "tga",
                                settings={"image_rotation": 90}, input_types=IMG_IN)
    fcutil.assert_done(job)
    assert fcutil.image_dims(job.output_path) == (240, 320)


def test_multipage_pdf_emits_one_jp2_per_page(tmp_path, sample_pdf2):
    """A 2-page PDF must produce TWO distinct image files, not one that
    overwrites the other (multi-page collision regression)."""
    import os
    job = fcutil.run_conversion(tmp_path, sample_pdf2, "jp2", input_types=["pdf"])
    fcutil.assert_done(job)
    assert len(job.output_paths) == 2
    assert len(set(job.output_paths)) == 2
    assert all(os.path.exists(p) for p in job.output_paths)
    assert all(fcutil.image_format(p) == "JP2" for p in job.output_paths)


def test_multipage_pdf_emits_one_tga_per_page(tmp_path, sample_pdf2):
    import os
    job = fcutil.run_conversion(tmp_path, sample_pdf2, "tga", input_types=["pdf"])
    fcutil.assert_done(job)
    assert len(job.output_paths) == 2
    assert all(os.path.exists(p) for p in job.output_paths)


def test_jp2_quality_affects_size(tmp_path, sample_image):
    hi = fcutil.run_conversion(tmp_path / "hi", sample_image, "jp2",
                               settings={"image_quality": 90}, input_types=IMG_IN)
    lo = fcutil.run_conversion(tmp_path / "lo", sample_image, "jp2",
                               settings={"image_quality": 20}, input_types=IMG_IN)
    fcutil.assert_done(hi)
    fcutil.assert_done(lo)
    import os
    assert os.path.getsize(hi.output_path) > os.path.getsize(lo.output_path)

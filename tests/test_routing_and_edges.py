"""Cross-cutting behaviour: routing, output-path edge cases, config merge, cancel."""

import os

import pytest
import yaml

import fcutil
from fileconverter import helpers
from fileconverter.jobs.base import ConversionState
from fileconverter.jobs.factory import create_job
from fileconverter.jobs.ffmpeg import FFmpegJob
from fileconverter.jobs.gif import GifJob
from fileconverter.jobs.imagemagick import ImageMagickJob
from fileconverter.jobs.libreoffice import LibreOfficeJob
from fileconverter.presets import ConversionPreset

_DEFAULTS = yaml.safe_load(open("fileconverter/resources/default_presets.yaml"))["presets"]
_BACKENDS = (FFmpegJob, GifJob, ImageMagickJob, LibreOfficeJob)


# --- OUTPUT_TYPES / preset wiring (no external tools needed) ---------------

def test_new_output_types_registered():
    for t in ["aiff", "wma", "ac3", "jp2", "tga", "txt", "rtf", "html", "epub", "csv"]:
        assert t in helpers.OUTPUT_TYPES


def test_new_doc_outputs_in_libreoffice_set():
    for t in ["txt", "csv", "rtf", "epub", "html"]:
        assert t in helpers.LIBREOFFICE_OUTPUTS


@pytest.mark.parametrize("preset", _DEFAULTS, ids=lambda p: p["name"])
def test_default_preset_output_type_is_known(preset):
    assert preset["output_type"] in helpers.OUTPUT_TYPES


@pytest.mark.parametrize("preset", _DEFAULTS, ids=lambda p: p["name"])
def test_default_preset_routes_to_a_backend(preset):
    p = ConversionPreset.from_dict(preset)
    job = create_job(p, f"/tmp/sample.{p.input_types[0]}", hw_accel="off")
    assert isinstance(job, _BACKENDS)


# --- Hardware-accel routing -------------------------------------------------

@pytest.mark.parametrize("codec,expect", [
    ("h264", "nvenc"), ("hevc", "nvenc"), ("h265", "nvenc"),
    ("av1", "off"), ("prores", "off"),
])
def test_factory_enables_hw_only_for_h26x(codec, expect):
    p = ConversionPreset(name="x", output_type="mp4", input_types=["mp4"],
                         settings={"video_codec": codec})
    job = create_job(p, "/tmp/x.mp4", hw_accel="nvenc")
    assert job._hw_accel == expect


def test_audio_output_never_gets_hw_accel():
    p = ConversionPreset(name="x", output_type="aiff", input_types=["wav"])
    job = create_job(p, "/tmp/x.wav", hw_accel="nvenc")
    assert job._hw_accel == "off"


# --- White-box: ProRes pixel-format pin ------------------------------------

def test_transform_args_prores_skips_yuv420p_pin():
    p = ConversionPreset(name="x", output_type="mov", input_types=["mp4"],
                         settings={"video_scale": 0.5})
    job = FFmpegJob(p, "/tmp/x.mp4")
    assert "format=yuv420p" not in job._transform_args(pin_format=None)
    # default still pins yuv420p for mp4/mkv/mov
    assert "format=yuv420p" in job._transform_args()


# --- Output path edge cases -------------------------------------------------

@pytest.mark.skipif(not fcutil.HAS_FFMPEG, reason="ffmpeg required")
@pytest.mark.parametrize("name", [
    "with space.wav",
    "caffè €.wav",
    "weird (1) & $name.wav",
    "日本語.wav",
    "trailing.dots..wav",
])
def test_filenames_with_special_chars(tmp_path, sample_audio, name):
    """Arg-list subprocess calls must handle spaces/unicode/shell metachars."""
    job = fcutil.run_conversion(tmp_path, sample_audio, "aiff", dest_name=name)
    fcutil.assert_done(job)
    assert fcutil.codec_name(job.output_path, "audio") == "pcm_s16be"


@pytest.mark.skipif(not fcutil.HAS_FFMPEG, reason="ffmpeg required")
def test_output_collision_gets_unique_name(tmp_path, sample_audio):
    j1 = fcutil.run_conversion(tmp_path, sample_audio, "aiff")
    j2 = fcutil.run_conversion(tmp_path, sample_audio, "aiff")
    fcutil.assert_done(j1)
    fcutil.assert_done(j2)
    assert j1.output_path != j2.output_path
    assert os.path.exists(j1.output_path) and os.path.exists(j2.output_path)


@pytest.mark.skipif(not fcutil.HAS_FFMPEG, reason="ffmpeg required")
def test_post_action_delete_removes_input(tmp_path, sample_audio):
    job = fcutil.run_conversion(tmp_path, sample_audio, "aiff", post_action="delete")
    fcutil.assert_done(job)
    assert not os.path.exists(job.input_path)
    assert os.path.exists(job.output_path)


# --- Cancel -----------------------------------------------------------------

@pytest.mark.skipif(not fcutil.HAS_FFMPEG, reason="ffmpeg required")
def test_cancel_before_run_fails_and_cleans_up(tmp_path, sample_video):
    import shutil
    src = tmp_path / "clip.mp4"
    shutil.copy2(sample_video, src)
    p = ConversionPreset(name="x", output_type="mp4", input_types=["mp4"],
                         settings={"video_encoding_speed": "ultrafast"})
    job = create_job(p, str(src), hw_accel="off")
    job.prepare()
    declared = list(job.output_paths)
    job.request_cancel()
    job.run()
    assert job.state == ConversionState.FAILED
    for path in declared:
        assert not os.path.exists(path)


# --- Multi-output path generation (PDF page-collision regression) -----------

def test_generate_unique_path_honours_reserved_set(tmp_path):
    from fileconverter.path_helpers import generate_unique_path
    p = str(tmp_path / "x.jp2")
    a = generate_unique_path(p, reserved=set())
    assert a == p
    b = generate_unique_path(p, reserved={a})
    assert b != a  # reserved path is skipped even though no file exists yet


def test_multipage_prepare_assigns_distinct_paths(tmp_path, monkeypatch):
    """A multi-output job whose template lacks a page token must still produce
    distinct, page-numbered output paths (regression: PDF pages collided and
    overwrote each other)."""
    from fileconverter.jobs.base import ConversionJob
    src = tmp_path / "doc.pdf"
    src.write_bytes(b"%PDF-1.4 not-a-real-pdf")
    preset = ConversionPreset(name="t", output_type="jp2", input_types=["pdf"])
    job = ConversionJob(preset, str(src))
    monkeypatch.setattr(job, "_get_output_files_count", lambda: 3)
    job.prepare()
    names = [os.path.basename(p) for p in job.output_paths]
    assert names == ["doc-1.jp2", "doc-2.jp2", "doc-3.jp2"]
    assert len(set(job.output_paths)) == 3  # all distinct


def test_single_output_keeps_plain_name(tmp_path, monkeypatch):
    from fileconverter.jobs.base import ConversionJob
    src = tmp_path / "doc.pdf"
    src.write_bytes(b"%PDF-1.4")
    preset = ConversionPreset(name="t", output_type="png", input_types=["pdf"])
    job = ConversionJob(preset, str(src))
    monkeypatch.setattr(job, "_get_output_files_count", lambda: 1)
    job.prepare()
    assert [os.path.basename(p) for p in job.output_paths] == ["doc.png"]


# --- Invalid codec/container combinations -----------------------------------

@pytest.mark.parametrize("codec,container", [("av1", "mov"), ("prores", "mp4")])
def test_invalid_codec_container_raises(codec, container):
    from fileconverter.jobs.ffmpeg import FFmpegJob
    preset = ConversionPreset(name="t", output_type=container, input_types=["mp4"],
                              settings={"video_codec": codec})
    job = FFmpegJob(preset, "/tmp/x.mp4")
    job.output_paths = [f"/tmp/o.{container}"]
    with pytest.raises(RuntimeError, match="cannot be stored"):
        job._build_arguments()


@pytest.mark.parametrize("codec,container", [
    ("h264", "mp4"), ("hevc", "mkv"), ("hevc", "mov"),
    ("av1", "mp4"), ("av1", "mkv"), ("prores", "mov"), ("prores", "mkv"),
])
def test_valid_codec_container_builds(codec, container):
    from fileconverter.jobs.ffmpeg import FFmpegJob
    preset = ConversionPreset(name="t", output_type=container, input_types=["mp4"],
                              settings={"video_codec": codec})
    job = FFmpegJob(preset, "/tmp/x.mp4")
    job.output_paths = [f"/tmp/o.{container}"]
    job._build_arguments()  # must not raise
    assert job._passes


def test_video_codec_null_does_not_crash():
    """A hand-edited `video_codec:` (None) must fall back to h264, not crash."""
    from fileconverter.jobs.ffmpeg import FFmpegJob
    preset = ConversionPreset(name="t", output_type="mp4", input_types=["mp4"],
                              settings={"video_codec": None})
    job = FFmpegJob(preset, "/tmp/x.mp4")
    job.output_paths = ["/tmp/o.mp4"]
    job._build_arguments()
    assert any("libx264" in p.arguments for p in job._passes)


# --- Config upgrade merge ---------------------------------------------------

def test_load_settings_appends_new_presets(tmp_path, monkeypatch):
    """An older config missing the new presets gains them on load."""
    import fileconverter.config as cfg
    cfg_file = tmp_path / "settings.yaml"
    old = {
        "version": 1,
        "presets": [
            {"name": "To Mp4", "output_type": "mp4", "input_types": ["mkv"], "settings": {}},
        ],
    }
    cfg_file.write_text(yaml.dump(old))
    monkeypatch.setattr(cfg, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(cfg, "CONFIG_FILE", cfg_file)

    settings = cfg.load_settings()
    names = {p.name for p in settings.presets}
    for expected in ["To Mp4 (H.265)", "To Epub", "To Aiff", "To Jp2", "To Csv"]:
        assert expected in names, f"{expected} not merged in"

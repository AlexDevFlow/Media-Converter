"""New video codecs: H.265/HEVC, AV1, ProRes — plus codec routing & hw fallback."""

import pytest

import fcutil

pytestmark = pytest.mark.skipif(not fcutil.HAS_FFMPEG, reason="ffmpeg required")

# Any of these may be an input to a video preset.
VID_IN = ["mp4", "mkv", "mov", "webm", "avi", "gif"]
FAST = {"video_encoding_speed": "ultrafast"}

need_x265 = pytest.mark.skipif(not fcutil.encoder_available("libx265"),
                               reason="libx265 required")
need_av1 = pytest.mark.skipif(not fcutil.encoder_available("libsvtav1"),
                              reason="svt-av1 required")
need_prores = pytest.mark.skipif(not fcutil.encoder_available("prores_ks"),
                                 reason="prores_ks required")


def test_default_mp4_codec_is_h264(tmp_path, sample_video):
    """No video_codec setting => H.264 (backward compatible)."""
    job = fcutil.run_conversion(tmp_path, sample_video, "mp4",
                                settings=FAST, input_types=VID_IN)
    fcutil.assert_done(job)
    assert fcutil.codec_name(job.output_path, "video") == "h264"


@need_x265
def test_h265_mp4_is_hevc_with_hvc1_tag(tmp_path, sample_video):
    job = fcutil.run_conversion(
        tmp_path, sample_video, "mp4",
        settings={"video_codec": "hevc", "video_quality": 28, "enable_audio": True, **FAST},
        input_types=VID_IN)
    fcutil.assert_done(job)
    out = job.output_path
    assert fcutil.codec_name(out, "video") == "hevc"
    # hvc1 tag is what makes HEVC play in QuickTime/Safari/Finder.
    assert fcutil.has_codec_tag(out, "hvc1")
    assert fcutil.codec_name(out, "audio") == "aac"


@need_x265
def test_h265_mkv_has_no_hvc1_tag(tmp_path, sample_video):
    job = fcutil.run_conversion(
        tmp_path, sample_video, "mkv",
        settings={"video_codec": "hevc", **FAST}, input_types=VID_IN)
    fcutil.assert_done(job)
    assert fcutil.codec_name(job.output_path, "video") == "hevc"
    assert not fcutil.has_codec_tag(job.output_path, "hvc1")


@need_x265
def test_h265_alias_h265_string(tmp_path, sample_video):
    """video_codec='h265' should be accepted as an alias for 'hevc'."""
    job = fcutil.run_conversion(
        tmp_path, sample_video, "mp4",
        settings={"video_codec": "h265", **FAST}, input_types=VID_IN)
    fcutil.assert_done(job)
    assert fcutil.codec_name(job.output_path, "video") == "hevc"


@need_av1
def test_av1_mp4(tmp_path, sample_video):
    job = fcutil.run_conversion(
        tmp_path, sample_video, "mp4",
        settings={"video_codec": "av1", "video_quality": 33, **FAST}, input_types=VID_IN)
    fcutil.assert_done(job)
    assert fcutil.codec_name(job.output_path, "video") == "av1"


@need_av1
def test_av1_ignores_forced_gpu(tmp_path, sample_video):
    """AV1 is CPU-only here: even with hw_accel=nvenc it must encode on CPU."""
    job = fcutil.run_conversion(
        tmp_path, sample_video, "mp4",
        settings={"video_codec": "av1", "video_quality": 40, **FAST},
        input_types=VID_IN, hw_accel="nvenc")
    fcutil.assert_done(job)
    assert fcutil.codec_name(job.output_path, "video") == "av1"


@need_prores
def test_prores_mov_keeps_high_bitdepth_and_pcm(tmp_path, sample_video):
    job = fcutil.run_conversion(
        tmp_path, sample_video, "mov",
        settings={"video_codec": "prores", "prores_profile": 3}, input_types=VID_IN)
    fcutil.assert_done(job)
    out = job.output_path
    assert fcutil.codec_name(out, "video") == "prores"
    pf = fcutil.pix_fmt(out)
    # ProRes opted out of the yuv420p pin: HQ profile keeps 10-bit 4:2:2.
    assert pf != "yuv420p" and "422" in pf
    assert fcutil.codec_name(out, "audio") == "pcm_s16le"


def test_disable_audio_drops_audio_stream(tmp_path, sample_video):
    job = fcutil.run_conversion(
        tmp_path, sample_video, "mp4",
        settings={"enable_audio": False, **FAST}, input_types=VID_IN)
    fcutil.assert_done(job)
    assert not fcutil.has_stream(job.output_path, "audio")


def test_video_scale_produces_even_dims(tmp_path, sample_video):
    job = fcutil.run_conversion(
        tmp_path, sample_video, "mp4",
        settings={"video_scale": 0.5, **FAST}, input_types=VID_IN)
    fcutil.assert_done(job)
    assert fcutil.video_dims(job.output_path) == (160, 120)


def test_video_rotation_90_swaps_dims(tmp_path, sample_video):
    job = fcutil.run_conversion(
        tmp_path, sample_video, "mp4",
        settings={"video_rotation": 90, **FAST}, input_types=VID_IN)
    fcutil.assert_done(job)
    assert fcutil.video_dims(job.output_path) == (240, 320)


def test_hw_nvenc_falls_back_to_software(tmp_path, sample_video):
    """Forcing NVENC with no usable GPU must transparently fall back to libx264.

    Holds on GPU machines too: NVENC also produces an h264 stream.
    """
    job = fcutil.run_conversion(
        tmp_path, sample_video, "mp4",
        settings=FAST, input_types=VID_IN, hw_accel="nvenc")
    fcutil.assert_done(job)
    assert fcutil.codec_name(job.output_path, "video") == "h264"


@need_x265
def test_h265_hw_falls_back_to_software(tmp_path, sample_video):
    job = fcutil.run_conversion(
        tmp_path, sample_video, "mp4",
        settings={"video_codec": "hevc", **FAST}, input_types=VID_IN, hw_accel="nvenc")
    fcutil.assert_done(job)
    assert fcutil.codec_name(job.output_path, "video") == "hevc"
    assert fcutil.has_codec_tag(job.output_path, "hvc1")

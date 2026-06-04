"""New audio outputs: AIFF, WMA, AC3, ALAC."""

import os

import pytest

import fcutil

pytestmark = pytest.mark.skipif(not fcutil.HAS_FFMPEG, reason="ffmpeg required")


def test_aiff_16bit_from_audio(tmp_path, sample_audio):
    job = fcutil.run_conversion(tmp_path, sample_audio, "aiff",
                                settings={"audio_encoding_mode": "aiff16"})
    fcutil.assert_done(job)
    assert job.output_path.endswith(".aiff")
    assert fcutil.codec_name(job.output_path, "audio") == "pcm_s16be"
    assert "aiff" in fcutil.format_name(job.output_path)


def test_aiff_24bit(tmp_path, sample_audio):
    job = fcutil.run_conversion(tmp_path, sample_audio, "aiff",
                                settings={"audio_encoding_mode": "aiff24"})
    fcutil.assert_done(job)
    assert fcutil.codec_name(job.output_path, "audio") == "pcm_s24be"


def test_aiff_unknown_mode_defaults_to_16bit(tmp_path, sample_audio):
    job = fcutil.run_conversion(tmp_path, sample_audio, "aiff",
                                settings={"audio_encoding_mode": "bogus"})
    fcutil.assert_done(job)
    assert fcutil.codec_name(job.output_path, "audio") == "pcm_s16be"


def test_aiff_extracts_audio_from_video(tmp_path, sample_video):
    """Audio-only target must drop the video stream (-vn)."""
    job = fcutil.run_conversion(tmp_path, sample_video, "aiff", input_types=["mp4"])
    fcutil.assert_done(job)
    assert fcutil.has_stream(job.output_path, "audio")
    assert not fcutil.has_stream(job.output_path, "video")


@pytest.mark.skipif(not fcutil.encoder_available("wmav2"), reason="wmav2 encoder required")
def test_wma(tmp_path, sample_audio):
    job = fcutil.run_conversion(tmp_path, sample_audio, "wma",
                                settings={"audio_bitrate": 160})
    fcutil.assert_done(job)
    assert fcutil.codec_name(job.output_path, "audio") == "wmav2"
    assert "asf" in fcutil.format_name(job.output_path)


@pytest.mark.skipif(not fcutil.encoder_available("wmav2"), reason="wmav2 encoder required")
def test_wma_bitrate_affects_size(tmp_path, sample_audio):
    hi = fcutil.run_conversion(tmp_path / "hi", sample_audio, "wma",
                               settings={"audio_bitrate": 192})
    lo = fcutil.run_conversion(tmp_path / "lo", sample_audio, "wma",
                               settings={"audio_bitrate": 48})
    fcutil.assert_done(hi)
    fcutil.assert_done(lo)
    assert os.path.getsize(hi.output_path) > os.path.getsize(lo.output_path)


@pytest.mark.skipif(not fcutil.encoder_available("ac3"), reason="ac3 encoder required")
def test_ac3(tmp_path, sample_audio):
    job = fcutil.run_conversion(tmp_path, sample_audio, "ac3",
                                settings={"audio_bitrate": 192})
    fcutil.assert_done(job)
    assert fcutil.codec_name(job.output_path, "audio") == "ac3"


@pytest.mark.skipif(not fcutil.encoder_available("alac"), reason="alac encoder required")
def test_alac_m4a_lossless(tmp_path, sample_audio):
    job = fcutil.run_conversion(tmp_path, sample_audio, "m4a",
                                settings={"audio_codec": "alac"})
    fcutil.assert_done(job)
    assert job.output_path.endswith(".m4a")
    assert fcutil.codec_name(job.output_path, "audio") == "alac"
    assert not fcutil.has_stream(job.output_path, "video")


def test_m4a_without_codec_setting_stays_aac(tmp_path, sample_audio):
    """Backward compatibility: existing M4A preset must keep producing AAC."""
    job = fcutil.run_conversion(tmp_path, sample_audio, "m4a")
    fcutil.assert_done(job)
    assert fcutil.codec_name(job.output_path, "audio") == "aac"


def test_audio_channel_downmix_to_mono(tmp_path, sample_audio):
    job = fcutil.run_conversion(tmp_path, sample_audio, "aiff",
                                settings={"audio_channel_count": 1})
    fcutil.assert_done(job)
    assert fcutil.channels(job.output_path) == 1


def test_audio_channel_zero_preserves_stereo(tmp_path, sample_audio):
    job = fcutil.run_conversion(tmp_path, sample_audio, "aiff",
                                settings={"audio_channel_count": 0})
    fcutil.assert_done(job)
    assert fcutil.channels(job.output_path) == 2

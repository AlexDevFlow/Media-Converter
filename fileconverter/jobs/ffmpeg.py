"""FFmpeg conversion backend — ported from ConversionJob_FFMPEG.cs."""

from __future__ import annotations
import glob
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass

from fileconverter.integration.install import install_hint
from fileconverter.jobs.base import ConversionJob
from fileconverter.path_helpers import generate_unique_path
from fileconverter.presets import ConversionPreset

_DURATION_RE = re.compile(
    r"Duration:\s*(\d{2}):(\d{2}):(\d{2})\.(\d{2}),.*bitrate:\s*(\d+)\s*kb/s"
)
_PROGRESS_RE = re.compile(
    r"size=\s*\d+.*time=(\d{2}):(\d{2}):(\d{2})\.(\d{2})\s+bitrate="
)

# --- Bitrate / quality mapping tables (from ConversionJob_FFMPEG.Converters.cs) ---

_MP3_VBR_MAP = {245: 0, 225: 1, 190: 2, 175: 3, 165: 4, 130: 5, 115: 6, 100: 7, 85: 8, 65: 9}
_OGG_VBR_MAP = {
    500: 10, 320: 9, 256: 8, 224: 7, 192: 6, 160: 5,
    128: 4, 112: 3, 96: 2, 80: 1, 64: 0, 48: -1, 32: -2,
}
_AAC_VBR_MAP = {
    460: "3.9", 340: "3", 256: "2.2", 224: "1.9", 192: "1.6", 155: "1.3",
    128: "1", 112: "0.9", 96: "0.75", 80: "0.6", 64: "0.45", 48: "0.3",
    32: "0.2", 16: "0.1",
}
_WAV_CODEC_MAP = {"wav8": "pcm_s8le", "wav16": "pcm_s16le", "wav24": "pcm_s24le", "wav32": "pcm_s32le"}

# NVENC encoding speed: maps VideoEncodingSpeed → NVENC preset (from original C#)
_NVENC_PRESET_MAP = {
    "ultrafast": "p1", "superfast": "p2", "veryfast": "p3",
    "faster": "p4", "fast": "p4", "medium": "p4",
    "slow": "p5", "slower": "p6", "veryslow": "p7",
}

# VAAPI doesn't have granular speed presets — map to compression_level (0=fast, 7=slow)
_VAAPI_COMPRESSION_MAP = {
    "ultrafast": 0, "superfast": 1, "veryfast": 2,
    "faster": 3, "fast": 3, "medium": 4,
    "slow": 5, "slower": 6, "veryslow": 7,
}

# Cache for hardware acceleration detection (avoids re-probing)
_hwaccel_cache: dict[str, bool] = {}


def _find_closest(table: dict, value: int):
    """Find the closest key in a mapping table and return its value."""
    if value in table:
        return table[value]
    closest = min(table.keys(), key=lambda k: abs(k - value))
    return table[closest]


def _vaapi_device() -> str:
    """Find the first available VAAPI render node."""
    nodes = sorted(glob.glob("/dev/dri/renderD*"))
    return nodes[0] if nodes else "/dev/dri/renderD128"


def detect_hwaccel(encoder: str) -> bool:
    """Test if a hardware encoder actually works by running a tiny encode.

    Results are cached so we only probe once per session.
    """
    if encoder in _hwaccel_cache:
        return _hwaccel_cache[encoder]

    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        _hwaccel_cache[encoder] = False
        return False

    # Build a minimal test command for each encoder type
    if encoder == "nvenc":
        cmd = [ffmpeg, "-y", "-f", "lavfi", "-i", "color=black:s=64x64:d=0.1",
               "-c:v", "h264_nvenc", "-preset", "p4", "-f", "null", "-"]
    elif encoder == "vaapi":
        cmd = [ffmpeg, "-y", "-vaapi_device", _vaapi_device(),
               "-f", "lavfi", "-i", "color=black:s=64x64:d=0.1",
               "-vf", "format=nv12,hwupload",
               "-c:v", "h264_vaapi", "-f", "null", "-"]
    else:
        _hwaccel_cache[encoder] = False
        return False

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        works = result.returncode == 0
    except (subprocess.TimeoutExpired, OSError):
        works = False

    _hwaccel_cache[encoder] = works
    return works


def resolve_hwaccel(setting: str) -> str:
    """Resolve the hardware acceleration setting to an actual mode.

    Args:
        setting: "off", "auto", "nvenc", or "vaapi"

    Returns:
        "off", "nvenc", or "vaapi" — the resolved mode that actually works.
    """
    if setting == "off":
        return "off"

    if setting == "auto":
        # Prefer NVENC (usually faster), fall back to VAAPI
        if detect_hwaccel("nvenc"):
            return "nvenc"
        if detect_hwaccel("vaapi"):
            return "vaapi"
        return "off"

    # Specific encoder requested — verify it works
    if setting in ("nvenc", "vaapi") and detect_hwaccel(setting):
        return setting

    return "off"


@dataclass
class _FFmpegPass:
    name: str
    arguments: list[str]
    file_to_delete: str = ""


class FFmpegJob(ConversionJob):
    def __init__(self, preset: ConversionPreset, input_path: str, hw_accel: str = "off"):
        super().__init__(preset, input_path)
        self._passes: list[_FFmpegPass] = []
        self._duration_seconds: float = 0.0
        self._hw_accel: str = hw_accel  # "off", "nvenc", or "vaapi"

    @staticmethod
    def _find_ffmpeg() -> str:
        path = shutil.which("ffmpeg")
        if not path:
            raise FileNotFoundError(f"ffmpeg not found in PATH. {install_hint('ffmpeg')}")
        return path

    def _initialize(self) -> None:
        self._build_arguments()

    def _build_arguments(self) -> None:
        """Build ffmpeg argument lists for each pass."""
        base = ["-n"]
        preset = self.preset

        custom_enabled = preset.get_setting_bool("enable_ffmpeg_custom_command", False)
        if custom_enabled:
            custom_cmd = preset.get_setting("ffmpeg_custom_command", "")
            if custom_cmd:
                args = base + ["-i", self.input_path] + custom_cmd.split() + [self.output_path]
                self._passes.append(_FFmpegPass("Conversion", args))
                return

        out_type = preset.output_type

        if out_type == "aac":
            self._build_aac(base)
        elif out_type == "avi":
            self._build_avi(base)
        elif out_type == "flac":
            self._build_flac(base)
        elif out_type == "gif":
            self._build_gif(base)
        elif out_type == "ico":
            self._build_ico(base)
        elif out_type == "mp3":
            self._build_mp3(base)
        elif out_type in ("mp4", "mkv"):
            self._build_h264(base)
        elif out_type == "ogg":
            self._build_ogg(base)
        elif out_type == "ogv":
            self._build_ogv(base)
        elif out_type == "wav":
            self._build_wav(base)
        elif out_type == "webm":
            self._build_webm(base)
        else:
            # Generic passthrough attempt
            args = base + ["-i", self.input_path, self.output_path]
            self._passes.append(_FFmpegPass("Conversion", args))

    # --- Audio channel args ---
    def _channel_args(self) -> list[str]:
        ch = self.preset.get_setting_int("audio_channel_count", 0)
        return ["-ac", str(ch)] if ch > 0 else []

    # --- Video transform filter args ---
    def _transform_args(self, hw_mode: str = "off") -> str:
        parts = []
        scale = self.preset.get_setting_float("video_scale", 1.0)
        out_type = self.preset.output_type

        if out_type in ("mp4", "mkv"):
            sf = f"{scale:#.2g}" if abs(scale - 1.0) >= 0.005 else "1"
            if hw_mode == "nvenc":
                # CUDA scale filter includes format conversion
                parts.append(f"scale_cuda=trunc(iw*{sf}/2)*2:trunc(ih*{sf}/2)*2:format=yuv420p")
            else:
                parts.append(f"scale=trunc(iw*{sf}/2)*2:trunc(ih*{sf}/2)*2")
        elif abs(scale - 1.0) >= 0.005:
            sf = f"{scale:#.2g}"
            parts.append(f"scale=iw*{sf}:ih*{sf}")

        rotation = self.preset.get_setting_float("video_rotation", 0)
        if abs(rotation - 90) <= 0.05:
            parts.append("transpose=2")
        elif abs(rotation - 180) <= 0.05:
            parts.append("vflip,hflip")
        elif abs(rotation - 270) <= 0.05:
            parts.append("transpose=1")

        # For H.264 in MP4/MKV, force yuv420p for broad player compatibility
        # NVENC/CUDA excluded: scale_cuda above already sets format=yuv420p
        if out_type in ("mp4", "mkv") and hw_mode != "nvenc":
            parts.append("format=yuv420p")

        return ",".join(parts)

    def _vf_args(self) -> list[str]:
        tf = self._transform_args()
        return ["-vf", tf] if tf else []

    # --- Per-format builders ---
    def _build_aac(self, base: list[str]) -> None:
        bitrate = self.preset.get_setting_int("audio_bitrate", 155)
        q = _find_closest(_AAC_VBR_MAP, bitrate)
        args = base + ["-i", self.input_path, "-c:a", "aac", "-q:a", str(q)]
        args += self._channel_args()
        args += ["-write_apetag", "1", self.output_path]
        self._passes.append(_FFmpegPass("Conversion", args))

    def _build_avi(self, base: list[str]) -> None:
        vq = self.preset.get_setting_int("video_quality", 15)
        bitrate = self.preset.get_setting_int("audio_bitrate", 165)
        tf = self._transform_args()
        audio = ["-an"]
        if self.preset.get_setting_bool("enable_audio", True):
            mp3q = _find_closest(_MP3_VBR_MAP, bitrate)
            audio = ["-c:a", "libmp3lame", "-qscale:a", str(mp3q)]
        vf = ["-vf", tf] if tf else []
        mpeg4q = 31 - vq
        args = base + ["-i", self.input_path, "-c:v", "mpeg4", "-vtag", "xvid",
                        "-qscale:v", str(mpeg4q)] + audio + vf
        args += ["-id3v2_version", "3", "-write_id3v1", "1", self.output_path]
        self._passes.append(_FFmpegPass("Conversion", args))

    def _build_flac(self, base: list[str]) -> None:
        args = base + ["-i", self.input_path, "-compression_level", "12"]
        args += self._channel_args() + [self.output_path]
        self._passes.append(_FFmpegPass("Conversion", args))

    def _build_gif(self, base: list[str]) -> None:
        """Two-pass GIF with palette generation."""
        fps = self.preset.get_setting_int("video_frames_per_second", 10)
        tf = self._transform_args()
        tf_fps = f"{tf},{f'fps={fps}'}" if tf else f"fps={fps}"

        palette = generate_unique_path(
            os.path.join(tempfile.gettempdir(), os.path.basename(self.input_path) + "-palette.png")
        )
        # Pass 1: palette
        args1 = base + ["-i", self.input_path, "-vf", f"{tf_fps},palettegen", palette]
        self._passes.append(_FFmpegPass("Indexing colors", args1))
        # Pass 2: gif
        args2 = base + ["-i", self.input_path, "-i", palette,
                         "-lavfi", f"{tf_fps},paletteuse", self.output_path]
        self._passes.append(_FFmpegPass("Conversion", args2, file_to_delete=palette))

    def _build_ico(self, base: list[str]) -> None:
        args = base + ["-i", self.input_path, self.output_path]
        self._passes.append(_FFmpegPass("Conversion", args))

    def _build_mp3(self, base: list[str]) -> None:
        mode = self.preset.get_setting("audio_encoding_mode", "mp3vbr").lower()
        bitrate = self.preset.get_setting_int("audio_bitrate", 190)
        if mode == "mp3cbr":
            enc = ["-codec:a", "libmp3lame", "-b:a", f"{bitrate}k"]
        else:
            q = _find_closest(_MP3_VBR_MAP, bitrate)
            enc = ["-codec:a", "libmp3lame", "-q:a", str(q)]
        args = base + ["-i", self.input_path] + enc + self._channel_args()
        args += ["-id3v2_version", "3", "-write_id3v1", "1", self.output_path]
        self._passes.append(_FFmpegPass("Conversion", args))

    def _build_h264(self, base: list[str]) -> None:
        vq = self.preset.get_setting_int("video_quality", 28)
        speed = self.preset.get_setting("video_encoding_speed", "medium").lower()
        bitrate = self.preset.get_setting_int("audio_bitrate", 155)
        crf = 51 - vq
        hw = self._hw_accel

        # Audio args (same regardless of hw mode)
        audio = ["-an"]
        if self.preset.get_setting_bool("enable_audio", True):
            aac_q = _find_closest(_AAC_VBR_MAP, bitrate)
            audio = ["-c:a", "aac", "-qscale:a", str(aac_q)]

        # Video transform filter args (hw-aware)
        transform = self._transform_args(hw_mode=hw)
        vf = ["-vf", transform] if transform else []

        # Build codec-specific args based on hardware mode
        hw_input_args = []  # Args that go BEFORE -i

        if hw == "nvenc":
            # NVIDIA NVENC — ported from original C# CUDA path
            nvenc_preset = _NVENC_PRESET_MAP.get(speed, "p4")
            codec_args = ["-c:v", "h264_nvenc",
                          "-preset", nvenc_preset,
                          "-rc", "constqp", "-qp", str(crf)]
            hw_input_args = ["-hwaccel", "cuda", "-hwaccel_output_format", "cuda"]

        elif hw == "vaapi":
            # VAAPI (AMD/Intel on Linux) — Linux replacement for AMF
            compression = _VAAPI_COMPRESSION_MAP.get(speed, 4)
            codec_args = ["-c:v", "h264_vaapi",
                          "-compression_level", str(compression),
                          "-qp", str(crf)]
            hw_input_args = ["-vaapi_device", _vaapi_device(),
                             "-hwaccel", "vaapi", "-hwaccel_output_format", "vaapi"]
            # VAAPI needs hwupload in the filter chain
            vaapi_filters = "format=nv12,hwupload"
            if transform:
                vf = ["-vf", f"{vaapi_filters},{transform}"]
            else:
                vf = ["-vf", vaapi_filters]

        else:
            # Software encoding (default, always works)
            codec_args = ["-c:v", "libx264", "-preset", speed, "-crf", str(crf)]

        args = base + hw_input_args + ["-i", self.input_path] + codec_args + audio + vf + [self.output_path]
        self._passes.append(_FFmpegPass("Conversion", args))

    def _build_ogg(self, base: list[str]) -> None:
        bitrate = self.preset.get_setting_int("audio_bitrate", 128)
        q = _find_closest(_OGG_VBR_MAP, bitrate)
        args = base + ["-i", self.input_path, "-vn",
                        "-codec:a", "libvorbis", "-qscale:a", str(q)]
        args += self._channel_args() + [self.output_path]
        self._passes.append(_FFmpegPass("Conversion", args))

    def _build_ogv(self, base: list[str]) -> None:
        vq = self.preset.get_setting_int("video_quality", 7)
        bitrate = self.preset.get_setting_int("audio_bitrate", 128)
        vf = self._vf_args()
        audio = ["-an"]
        if self.preset.get_setting_bool("enable_audio", True):
            ogg_q = _find_closest(_OGG_VBR_MAP, bitrate)
            audio = ["-codec:a", "libvorbis", "-qscale:a", str(ogg_q)]
        args = base + ["-i", self.input_path,
                        "-codec:v", "libtheora", "-qscale:v", str(vq)] + audio + vf
        args += [self.output_path]
        self._passes.append(_FFmpegPass("Conversion", args))

    def _build_wav(self, base: list[str]) -> None:
        mode = self.preset.get_setting("audio_encoding_mode", "wav16").lower()
        codec = _WAV_CODEC_MAP.get(mode, "pcm_s16le")
        args = base + ["-i", self.input_path, "-acodec", codec]
        args += self._channel_args() + [self.output_path]
        self._passes.append(_FFmpegPass("Conversion", args))

    def _build_webm(self, base: list[str]) -> None:
        vq = self.preset.get_setting_int("video_quality", 30)
        bitrate = self.preset.get_setting_int("audio_bitrate", 128)
        crf = 63 - vq
        if vq == 63:
            enc = ["-lossless", "1"]
        else:
            enc = ["-crf", str(crf), "-b:v", "0"]
        vf = self._vf_args()
        audio = ["-an"]
        if self.preset.get_setting_bool("enable_audio", True):
            ogg_q = _find_closest(_OGG_VBR_MAP, bitrate)
            audio = ["-c:a", "libvorbis", "-qscale:a", str(ogg_q)]
        args = base + ["-i", self.input_path, "-c:v", "libvpx-vp9"] + enc + audio + vf
        args += [self.output_path]
        self._passes.append(_FFmpegPass("Conversion", args))

    # --- Execution ---
    def _convert(self) -> None:
        try:
            self._run_passes()
        except RuntimeError:
            if self._hw_accel != "off" and not self.cancel_requested:
                # Hardware encoding failed — fall back to software and retry
                self.user_state = "HW failed, retrying with software..."
                self.progress = 0.0
                self._duration_seconds = 0.0
                self._hw_accel = "off"
                self._passes.clear()
                self._build_arguments()
                # Clean up any partial output from the failed attempt
                for p in self.output_paths:
                    if os.path.exists(p):
                        os.remove(p)
                self._run_passes()
            else:
                raise

    def _run_passes(self) -> None:
        ffmpeg = self._find_ffmpeg()
        files_to_clean = [p.file_to_delete for p in self._passes if p.file_to_delete]
        try:
            for i, p in enumerate(self._passes):
                if self.cancel_requested:
                    return
                self.user_state = p.name
                cmd = [ffmpeg] + p.arguments
                proc = subprocess.Popen(
                    cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                    text=True, bufsize=1,
                )
                last_lines = []
                try:
                    for line in proc.stderr:
                        if self.cancel_requested:
                            proc.kill()
                            proc.wait()
                            return
                        last_lines.append(line.rstrip())
                        if len(last_lines) > 10:
                            last_lines.pop(0)
                        self._parse_output(last_lines[-1])
                    proc.wait()
                except Exception:
                    proc.kill()
                    proc.wait()
                    raise

                if proc.returncode != 0 and not self.cancel_requested:
                    err = "\n".join(last_lines)
                    raise RuntimeError(f"ffmpeg exited with code {proc.returncode}: {err}")
        finally:
            for f in files_to_clean:
                if os.path.exists(f):
                    os.remove(f)

    def _parse_output(self, line: str) -> None:
        m = _DURATION_RE.search(line)
        if m:
            h, mi, s, cs = int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4))
            self._duration_seconds = h * 3600 + mi * 60 + s + cs / 100.0
            return

        if self._duration_seconds > 0:
            m = _PROGRESS_RE.search(line)
            if m:
                h, mi, s, cs = int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4))
                current = h * 3600 + mi * 60 + s + cs / 100.0
                self.progress = min(current / self._duration_seconds, 0.99)
                return

        # Error detection (same logic as original, stripping file names to avoid false positives)
        clean = line.replace(self.input_path, "").replace(self.output_path, "")
        if any(k in clean for k in ("Exiting.", "Unsupported dimensions", "No such file or directory")):
            raise RuntimeError(f"ffmpeg error: {line}")
        if "Error" in clean:
            if clean.startswith("Error while decoding stream") and "Invalid data found" in clean:
                return  # Normal for transport streams
            raise RuntimeError(f"ffmpeg error: {line}")

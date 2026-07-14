"""Driver for the native SwiftUI front-end (macOS).

Spawns `fileconverter-ui` (compiled at install time from
fileconverter/ui/native/FileConverterUI.swift) and drives it over a
JSON-lines protocol. Everything that matters — conversions, ETA math,
auto-close timing, translations — stays in Python; the Swift binary only
renders. If the binary is missing or misbehaves before conversions start,
callers fall back to the tkinter UI, then headless.
"""

from __future__ import annotations
import json
import os
import queue
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from fileconverter import i18n
from fileconverter.config import (
    HWACCEL_LABELS, HWACCEL_MODES, Settings, load_settings, save_settings,
)
from fileconverter.i18n import _
from fileconverter.jobs.base import ConversionJob, ConversionState

UI_BIN = Path.home() / ".local" / "share" / "fileconverter" / "bin" / "fileconverter-ui"

_POLL = 0.2


class NativeUIUnavailable(RuntimeError):
    pass


def available() -> bool:
    return UI_BIN.exists() and os.access(UI_BIN, os.X_OK)


def _spawn(mode: str) -> subprocess.Popen:
    if not available():
        raise NativeUIUnavailable("fileconverter-ui is not built")
    try:
        return subprocess.Popen(
            [str(UI_BIN), mode],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            text=True, bufsize=1,
        )
    except OSError as e:
        raise NativeUIUnavailable(str(e))


def _send(proc: subprocess.Popen, obj: dict) -> bool:
    try:
        proc.stdin.write(json.dumps(obj) + "\n")
        proc.stdin.flush()
        return True
    except (BrokenPipeError, OSError, ValueError):
        return False


def _start_reader(proc: subprocess.Popen) -> queue.Queue:
    q: queue.Queue = queue.Queue()

    def _read():
        try:
            for line in proc.stdout:
                line = line.strip()
                if not line:
                    continue
                try:
                    q.put(json.loads(line))
                except ValueError:
                    pass
        except (OSError, ValueError):
            pass
        q.put(None)  # EOF sentinel

    threading.Thread(target=_read, daemon=True).start()
    return q


def _handshake(proc: subprocess.Popen, q: queue.Queue, init: dict,
               timeout: float = 8.0) -> None:
    """Send init and wait for {"ready": true}. Raising here is safe — no
    conversion has started yet, so the caller can fall back to another UI."""
    if not _send(proc, init):
        _kill(proc)
        raise NativeUIUnavailable("could not talk to the UI process")
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            msg = q.get(timeout=0.2)
        except queue.Empty:
            if proc.poll() is not None:
                raise NativeUIUnavailable("UI process exited during startup")
            continue
        if msg is None:
            raise NativeUIUnavailable("UI closed its output during startup")
        if msg.get("ready"):
            return
    _kill(proc)
    raise NativeUIUnavailable("UI startup timed out")


def _kill(proc: subprocess.Popen) -> None:
    try:
        if proc.stdin:
            proc.stdin.close()
    except OSError:
        pass
    try:
        proc.wait(timeout=3)
    except subprocess.TimeoutExpired:
        proc.kill()
        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            pass


# ── Progress window ──

def _progress_text(job: ConversionJob) -> str:
    """Percent + ETA text — same math as the GTK/tkinter windows."""
    progress = job.progress
    elapsed = time.time() - job.start_time if job.start_time else 0
    if job.state == ConversionState.DONE:
        return _("Complete")
    if job.state == ConversionState.FAILED:
        return _("Failed")
    if progress > 0.01 and elapsed > 1:
        eta = (elapsed / progress) * (1 - progress)
        if eta < 60:
            eta_str = _("{seconds}s remaining").format(seconds=int(eta))
        else:
            eta_str = _("{minutes}m {seconds}s remaining").format(
                minutes=int(eta // 60), seconds=int(eta % 60))
        return f"{progress * 100:.0f}% — {eta_str}"
    return f"{progress * 100:.0f}%"


def _job_status(job: ConversionJob) -> str:
    if job.state == ConversionState.DONE:
        return f"→ {os.path.basename(job.output_path)}"
    if job.state == ConversionState.FAILED:
        return job.error_message or _("Unknown error")
    if job.state == ConversionState.READY:
        return _("Queued...")
    return job.user_state


def _summary_status(jobs: list) -> str:
    failed = sum(1 for j in jobs if j.state == ConversionState.FAILED)
    done = sum(1 for j in jobs if j.state == ConversionState.DONE)
    total = len(jobs)
    if failed:
        return _("{done}/{total} completed, {failed} failed").format(
            done=done, total=total, failed=failed)
    return _("{done}/{total} completed").format(done=done, total=total)


def run_with_progress(jobs: list, settings: Settings) -> None:
    proc = _spawn("progress")
    q = _start_reader(proc)
    init = {
        "type": "init",
        "title": "File Converter",
        "jobs": [{"id": i, "name": j.input_filename,
                  "out": j.preset.output_type.upper()}
                 for i, j in enumerate(jobs)],
        "strings": {
            "cancel": _("Cancel"),
            "cancelling": _("Cancelling..."),
            "keep_open": _("Keep open"),
            "waiting": _("Waiting..."),
        },
    }
    _handshake(proc, q, init)

    # UI confirmed — safe to start converting now.
    def _prepare_and_run(job: ConversionJob):
        try:
            job.prepare()
            job.run()
        except Exception as e:
            job.state = ConversionState.FAILED
            job.error_message = str(e)

    def _worker():
        with ThreadPoolExecutor(
                max_workers=settings.max_simultaneous_conversions) as pool:
            pool.map(_prepare_and_run, jobs)

    threading.Thread(target=_worker, daemon=True).start()

    last_sent: dict = {}
    close_at = None      # auto-close deadline (time.time())
    keep_open = False
    summary_shown = False

    def _push_updates() -> bool:
        alive = True
        for i, job in enumerate(jobs):
            payload = {
                "type": "update", "id": i,
                "progress": round(min(job.progress, 1.0), 3),
                "state": job.state.value,
                "progress_text": _progress_text(job),
                "status": _job_status(job),
            }
            if last_sent.get(i) != payload:
                last_sent[i] = payload
                if not _send(proc, payload):
                    alive = False
        return alive

    try:
        while True:
            # Drain UI events
            ui_gone = False
            while True:
                try:
                    msg = q.get_nowait()
                except queue.Empty:
                    break
                if msg is None or msg.get("closed"):
                    ui_gone = True
                    break
                if "cancel" in msg:
                    idx = msg["cancel"]
                    if isinstance(idx, int) and 0 <= idx < len(jobs):
                        jobs[idx].request_cancel()
                if msg.get("keep_open"):
                    keep_open = True
                    close_at = None
                    _send(proc, {"type": "summary",
                                 "text": _summary_status(jobs),
                                 "show_keep_open": False})

            if ui_gone:
                # Window closed — stop pending/running jobs (their run loop
                # kills the ffmpeg/magick subprocess) and give them a moment.
                for job in jobs:
                    if job.state not in (ConversionState.DONE, ConversionState.FAILED):
                        job.request_cancel()
                time.sleep(0.4)
                return

            if not _push_updates():
                return

            all_done = all(j.state in (ConversionState.DONE, ConversionState.FAILED)
                           for j in jobs)
            if all_done:
                if not summary_shown:
                    summary_shown = True
                    if settings.exit_when_done and not keep_open:
                        close_at = time.time() + settings.exit_delay_seconds
                    else:
                        _send(proc, {"type": "summary",
                                     "text": _summary_status(jobs),
                                     "show_keep_open": False})
                if close_at is not None:
                    remaining = int(round(close_at - time.time()))
                    if remaining <= 0:
                        _send(proc, {"type": "exit"})
                        return
                    _send(proc, {"type": "summary",
                                 "text": _("{status} — closing in {seconds}s").format(
                                     status=_summary_status(jobs), seconds=remaining),
                                 "show_keep_open": True})

            time.sleep(_POLL)
    finally:
        _kill(proc)


# ── Settings window ──

def _settings_payload(settings: Settings) -> dict:
    from fileconverter.helpers import (
        ALL_INPUT_EXTENSIONS, OUTPUT_TYPES, VIDEO_CODECS,
    )
    speeds = ["ultrafast", "superfast", "veryfast", "faster", "fast",
              "medium", "slow", "slower", "veryslow"]
    detected = i18n.detect_system_language() or ""
    detected_label = dict(i18n.SUPPORTED_LANGUAGES).get(detected)
    auto_label = (_("System default ({name})").format(name=detected_label)
                  if detected_label else _("System default"))
    lang_labels = [auto_label] + [
        label for code, label in i18n.SUPPORTED_LANGUAGES if code != "auto"]

    # Mirrors the GTK editor's common_settings table.
    setting_rows = [
        {"key": "video_codec", "label": _("Video Codec"),
         "kind": "choice", "options": VIDEO_CODECS},
        {"key": "video_quality", "label": _("Video Quality (0-63)"),
         "kind": "int", "min": 0, "max": 63, "default": 28},
        {"key": "video_encoding_speed", "label": _("Encoding Speed"),
         "kind": "choice", "options": speeds},
        {"key": "video_scale", "label": _("Video Scale"),
         "kind": "float", "min": 0.1, "max": 4.0, "step": 0.1, "default": 1.0},
        {"key": "video_rotation", "label": _("Rotation (degrees)"),
         "kind": "int", "min": 0, "max": 270, "default": 0},
        {"key": "audio_bitrate", "label": _("Audio Bitrate"),
         "kind": "int", "min": 16, "max": 500, "default": 155},
        {"key": "image_quality", "label": _("Image Quality (0-100)"),
         "kind": "int", "min": 0, "max": 100, "default": 85},
        {"key": "image_scale", "label": _("Image Scale"),
         "kind": "float", "min": 0.1, "max": 4.0, "step": 0.1, "default": 1.0},
        {"key": "enable_audio", "label": _("Enable Audio"),
         "kind": "bool", "default": True},
    ]
    return {
        "type": "init",
        "settings": settings.to_dict(),
        "meta": {
            "output_types": OUTPUT_TYPES,
            "extensions": ALL_INPUT_EXTENSIONS,
            "post_actions": ["none", "archive", "delete"],
            "hw_labels": [_(label) for label in HWACCEL_LABELS],
            "hw_modes": HWACCEL_MODES,
            "lang_labels": lang_labels,
            "lang_codes": i18n.LANGUAGE_CODES,
            "setting_rows": setting_rows,
            "new_preset": {
                "name": _("New Preset"),
                "output_type": "mp4",
                "input_types": ["avi", "mkv", "mov", "mp4", "webm"],
                "input_post_action": "none",
                "output_template": "(p)(f)",
                "settings": {"enable_audio": True, "video_quality": 28,
                             "video_encoding_speed": "medium",
                             "audio_bitrate": 155, "video_scale": 1.0},
            },
            "strings": {
                "title": _("File Converter — Settings"),
                "title_modified": _("File Converter — Settings *"),
                "title_saved": _("File Converter — Settings (saved)"),
                "global": _("Global"),
                "presets": _("Presets"),
                "add": _("Add"),
                "remove": _("Remove"),
                "save": _("Save"),
                "name": _("Name:"),
                "output": _("Output:"),
                "input_types": _("Input types:"),
                "conversion_settings": _("Conversion settings:"),
                "after_conversion": _("After conversion:"),
                "output_template": _("Output template:"),
                "template_hint": _("Variables: (p) path, (f) filename, (o) output ext, (i) input ext"),
                "max_jobs": _("Max jobs:"),
                "auto_close": _("Auto-close when done"),
                "gpu_accel": _("GPU accel:"),
                "language": _("Language:"),
                "select_preset": _("Select a preset to edit"),
            },
        },
    }


def run_settings() -> None:
    settings = load_settings()
    i18n.init(settings.language)

    proc = _spawn("settings")
    q = _start_reader(proc)
    _handshake(proc, q, _settings_payload(settings))

    try:
        while True:
            msg = q.get()
            if msg is None or msg.get("closed"):
                return
            if msg.get("action") == "save":
                data = msg.get("settings") or {}
                old_lang = settings.language
                data.setdefault("version", settings.version)
                data.setdefault("exit_delay_seconds", settings.exit_delay_seconds)
                settings = Settings.from_dict(data)
                save_settings(settings)
                try:
                    from fileconverter.integration.macos import refresh_services
                    refresh_services(quiet=True)
                except Exception:
                    pass
                if settings.language != old_lang:
                    i18n.init(settings.language)
                    # Full re-init so every label picks up the new language
                    # (the GTK/tkinter windows rebuild themselves the same way).
                    _send(proc, _settings_payload(settings))
                else:
                    _send(proc, {"type": "saved"})
    finally:
        _kill(proc)


# ── Preset picker ──

def run_picker(file_paths: list, compatible_presets: list,
               on_choice) -> None:
    """Show the native picker; call on_choice(preset_name) if one is chosen."""
    n = len(file_paths)
    info = (_("{count} file selected") if n == 1
            else _("{count} files selected")).format(count=n)
    init = {
        "type": "init",
        "title": _("File Converter — Select Preset"),
        "info": info,
        "presets": [{
            "name": p["name"],
            "short": p["name"].split("/")[-1],
            "folder": "/".join(p["name"].split("/")[:-1]),
            "out": p.get("output_type", "").upper(),
        } for p in compatible_presets],
        "strings": {"convert": _("Convert")},
    }
    proc = _spawn("pick")
    q = _start_reader(proc)
    _handshake(proc, q, init)
    try:
        while True:
            msg = q.get()
            if msg is None or msg.get("closed"):
                return
            preset = msg.get("preset")
            if preset:
                on_choice(preset)
                return
    finally:
        _kill(proc)

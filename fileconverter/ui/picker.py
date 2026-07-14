"""Preset picker entry point — native SwiftUI on macOS, tkinter fallback.

Usage: fileconverter-pick file1.avi file2.mkv
(backs the generic "File Converter…" Quick Action on macOS)
"""

from __future__ import annotations
import os
import shutil
import subprocess
import sys

from fileconverter import i18n


def _find_fileconverter() -> str:
    for path in [
        os.path.expanduser("~/.local/bin/fileconverter"),
        "/usr/local/bin/fileconverter",
        "/usr/bin/fileconverter",
    ]:
        if os.path.isfile(path) and os.access(path, os.X_OK):
            return path
    return shutil.which("fileconverter") or ""


def _launch_conversion(preset_name: str, file_paths: list) -> None:
    # On macOS, route through File Converter.app when it exists: the app
    # stays alive for the conversion, so TCC folder prompts (Downloads,
    # Desktop, ...) are attributed to "File Converter" instead of python3.x.
    if sys.platform == "darwin":
        host_app = os.path.expanduser("~/Applications/File Converter.app")
        if os.path.isdir(host_app):
            from urllib.parse import quote
            url = ("fileconverter://convert?preset=" + quote(preset_name)
                   + "".join("&f=" + quote(p) for p in file_paths))
            try:
                subprocess.run(["open", url], check=True, timeout=30)
                return
            except (subprocess.SubprocessError, OSError):
                pass  # fall back to the direct spawn below

    fc = _find_fileconverter()
    if fc:
        cmd = [fc, "--conversion-preset", preset_name] + file_paths
    else:
        cmd = [sys.executable, "-m", "fileconverter",
               "--conversion-preset", preset_name] + file_paths
    subprocess.Popen(cmd, start_new_session=True)


def main() -> None:
    files = sys.argv[1:]
    if not files:
        print("Usage: fileconverter-pick file1 file2 ...", file=sys.stderr)
        sys.exit(1)
    file_paths = [os.path.abspath(f) for f in files]

    from fileconverter.config import load_settings
    settings = load_settings()
    i18n.init(settings.language)

    # A file with no extension can't be converted by any preset. Including it
    # in the selection would otherwise queue a job that is guaranteed to fail,
    # so treat the whole selection as unconvertible (the Finder submenu is
    # conservative in exactly the same way).
    extensions = set()
    for f in file_paths:
        ext = os.path.splitext(f)[1]
        if not ext:
            extensions = set()
            break
        extensions.add(ext.lower().lstrip("."))

    compatible = [p.to_dict() for p in settings.presets
                  if p.accepts_all_extensions(sorted(extensions))]

    if sys.platform == "darwin":
        try:
            from fileconverter.ui import native_ui
            if native_ui.available():
                if not compatible:
                    from fileconverter.ui import notify
                    from fileconverter.i18n import _
                    notify(_("No compatible presets"),
                           _("No presets support all selected file types: {types}").format(
                               types=", ".join(sorted(extensions))))
                    return
                native_ui.run_picker(
                    file_paths, compatible,
                    lambda preset: _launch_conversion(preset, file_paths))
                return
        except Exception:
            pass  # fall through to tkinter
    else:
        # Linux: GTK is the native look; tkinter only when it's unavailable
        # (GH #5 — a missing GTK must never mean a traceback).
        try:
            from fileconverter.ui import preset_picker
            preset_picker.main()
            return
        except (ImportError, ValueError):
            pass

    from fileconverter.ui import preset_picker_tk
    preset_picker_tk.main()


if __name__ == "__main__":
    main()

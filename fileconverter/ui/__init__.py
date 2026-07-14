"""UI components — GTK 4 on Linux; native SwiftUI (with a tkinter fallback)
on macOS.

`run_with_progress_auto` / `run_settings_auto` try the platform's preferred
front-ends in order and raise `UINotAvailable` when no GUI can be shown, so
the CLI can fall back to headless mode (GH #5: a missing toolkit must never
crash a conversion).
"""

from __future__ import annotations
import subprocess
import sys


class UINotAvailable(RuntimeError):
    """No usable GUI toolkit (or no display) — callers should go headless."""


def _try_native(fn_name: str, *args):
    if sys.platform != "darwin":
        raise UINotAvailable("native UI is macOS-only")
    try:
        from fileconverter.ui import native_ui
    except ImportError as e:
        raise UINotAvailable(f"native UI not importable: {e}")
    if not native_ui.available():
        raise UINotAvailable("fileconverter-ui binary not built")
    try:
        if fn_name == "progress":
            native_ui.run_with_progress(*args)
        else:
            native_ui.run_settings(*args)
    except native_ui.NativeUIUnavailable as e:
        raise UINotAvailable(str(e))


def _try_tk(fn_name: str, *args):
    try:
        from fileconverter.ui import progress_window_tk, settings_window_tk
        module = {"progress": progress_window_tk, "settings": settings_window_tk}[fn_name]
    except ImportError as e:
        raise UINotAvailable(f"tkinter not available: {e}")
    try:
        if fn_name == "progress":
            module.run_with_progress(*args)
        else:
            module.run_settings(*args)
    except Exception as e:
        # tkinter raises TclError when there's no window server session
        # (ssh, cron); anything raised while *creating* the root window
        # means "no GUI", not "conversion failed".
        if type(e).__name__ == "TclError":
            raise UINotAvailable(f"no display: {e}")
        raise


def _try_gtk(fn_name: str, *args):
    try:
        if fn_name == "progress":
            from fileconverter.ui.progress_window import run_with_progress
            run_with_progress(*args)
        else:
            from fileconverter.ui.settings_window import run_settings
            run_settings(*args)
    except (ImportError, ValueError) as e:
        raise UINotAvailable(f"GTK not available: {e}")


def run_with_progress_auto(jobs, settings) -> None:
    """Show the progress window with whichever front-end this platform has."""
    order = ["native", "tk"] if sys.platform == "darwin" else ["gtk", "tk"]
    last = None
    for toolkit in order:
        try:
            if toolkit == "native":
                return _try_native("progress", jobs, settings)
            if toolkit == "gtk":
                return _try_gtk("progress", jobs, settings)
            return _try_tk("progress", jobs, settings)
        except UINotAvailable as e:
            last = e
    raise last or UINotAvailable("no GUI toolkit available")


def run_settings_auto() -> None:
    order = ["native", "tk"] if sys.platform == "darwin" else ["gtk", "tk"]
    last = None
    for toolkit in order:
        try:
            if toolkit == "native":
                return _try_native("settings")
            if toolkit == "gtk":
                return _try_gtk("settings")
            return _try_tk("settings")
        except UINotAvailable as e:
            last = e
    raise last or UINotAvailable("no GUI toolkit available")


def notify(title: str, message: str) -> None:
    """Best-effort desktop notification (used by headless Finder launches)."""
    try:
        if sys.platform == "darwin":
            def esc(s: str) -> str:
                return s.replace("\\", "\\\\").replace('"', '\\"')
            subprocess.run(
                ["osascript", "-e",
                 f'display notification "{esc(message)}" with title "{esc(title)}"'],
                capture_output=True, timeout=10,
            )
        else:
            subprocess.run(["notify-send", title, message],
                           capture_output=True, timeout=10)
    except (subprocess.SubprocessError, OSError, FileNotFoundError):
        pass

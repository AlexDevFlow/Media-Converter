"""Environment sanitising for external tool subprocesses.

GH #6: in a PyInstaller onefile build, the bootloader points LD_LIBRARY_PATH
at the extraction directory so the frozen Python can find *its* bundled
libraries (GTK, Pango, HarfBuzz, Fontconfig, ...). Any child process inherits
that variable — so the system's /usr/bin/magick would load OUR HarfBuzz and
Fontconfig instead of the distro's. On a rolling-release system whose
libraqm expects a newer HarfBuzz, that fails outright:

    /usr/bin/magick: symbol lookup error: /usr/lib/libraqm.so.0:
    undefined symbol: hb_ft_font_get_ft_face

and the mismatched Fontconfig produces the "invalid attribute 'xsi:nil'"
warning wall. Building from source has neither problem — no bundled libs, no
injected loader path — which is exactly what the bug report observed.

ffmpeg / ImageMagick / Ghostscript / LibreOffice are system binaries, so they
must run with the environment the user's shell would have given them: restore
what PyInstaller saved in *_ORIG, and drop the variables we inject.
"""

from __future__ import annotations
import os
import sys

# PyInstaller stashes the pre-launch value of each of these in <VAR>_ORIG
# (only when the variable was set before launch).
_LOADER_VARS = (
    "LD_LIBRARY_PATH",     # Linux
    "DYLD_LIBRARY_PATH",   # macOS
    "DYLD_FRAMEWORK_PATH",
    "LIBPATH",             # AIX
)

# Runtime paths a frozen bundle sets for its own GTK/GI stack. They are
# meaningless — and actively harmful — for a system binary.
_BUNDLE_VARS = (
    "GI_TYPELIB_PATH",
    "GTK_PATH",
    "GTK_EXE_PREFIX",
    "GTK_DATA_PREFIX",
    "GDK_PIXBUF_MODULE_FILE",
    "GDK_PIXBUF_MODULEDIR",
    "FONTCONFIG_FILE",
    "FONTCONFIG_PATH",
)


def is_frozen() -> bool:
    return getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS")


class Cancelled(RuntimeError):
    """The user cancelled while an external tool was running."""


def run_cancellable(cmd, job, timeout: float = 600.0, poll: float = 0.1):
    """Run an external tool, killing it if the job is cancelled.

    subprocess.run() blocks until the tool exits, so a cancel (window closed,
    Cancel clicked) could not stop ImageMagick or LibreOffice: the batch kept
    converting with no window, and the results were then deleted as a
    cancelled job.

    Reader threads drain stdout/stderr (a tool that fills a pipe buffer would
    otherwise deadlock), while the main loop polls for exit, cancellation and
    the timeout. Note communicate(timeout=...) cannot be used in a poll loop:
    a retry after TimeoutExpired blocks until the process exits.

    Returns a CompletedProcess; raises Cancelled if the tool was killed.
    """
    import os
    import signal
    import subprocess
    import threading
    import time

    if job is not None and job.cancel_requested:
        raise Cancelled()

    # Own process group: the tools we drive spawn children (soffice is a shell
    # wrapper around soffice.bin), and killing only the parent would leave the
    # real worker running — still holding the pipes open, so we'd block anyway.
    proc = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, env=system_env(), start_new_session=True,
    )

    def _kill_tree() -> None:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except (OSError, ProcessLookupError):
            try:
                proc.kill()
            except OSError:
                pass

    chunks: dict = {"out": [], "err": []}

    def _drain(stream, key):
        try:
            for line in stream:
                chunks[key].append(line)
        except (OSError, ValueError):
            pass
        finally:
            try:
                stream.close()
            except OSError:
                pass

    readers = [
        threading.Thread(target=_drain, args=(proc.stdout, "out"), daemon=True),
        threading.Thread(target=_drain, args=(proc.stderr, "err"), daemon=True),
    ]
    for t in readers:
        t.start()

    deadline = time.monotonic() + timeout
    killed_reason = None
    try:
        while proc.poll() is None:
            if job is not None and job.cancel_requested:
                killed_reason = "cancelled"
                break
            if time.monotonic() > deadline:
                killed_reason = "timeout"
                break
            time.sleep(poll)
    finally:
        if killed_reason is not None or proc.poll() is None:
            _kill_tree()
        proc.wait()
        for t in readers:
            t.join(timeout=5)

    if killed_reason == "cancelled":
        raise Cancelled()
    if killed_reason == "timeout":
        raise subprocess.TimeoutExpired(cmd, timeout)

    return subprocess.CompletedProcess(
        cmd, proc.returncode, "".join(chunks["out"]), "".join(chunks["err"])
    )


def system_env(extra: dict | None = None) -> dict | None:
    """Environment for running a *system* tool (ffmpeg, magick, gs, soffice).

    Returns None when running from source and no overrides are requested —
    letting subprocess inherit os.environ unchanged, which is what we want.
    """
    if not is_frozen():
        if not extra:
            return None
        env = os.environ.copy()
        env.update(extra)
        return env

    env = os.environ.copy()

    for var in _LOADER_VARS:
        original = env.pop(f"{var}_ORIG", None)
        if original:
            env[var] = original          # restore the user's own value
        else:
            env.pop(var, None)           # there was none — remove ours

    for var in _BUNDLE_VARS:
        meipass = getattr(sys, "_MEIPASS", "")
        # Only drop it if it actually points into our bundle; a value the user
        # set themselves is none of our business.
        if meipass and env.get(var, "").startswith(meipass):
            env.pop(var, None)

    if extra:
        env.update(extra)
    return env

"""Output path generation — ported from PathHelpers.cs."""

from __future__ import annotations
import os
import re
import sys
import threading
from datetime import datetime
from pathlib import Path

_DATE_RE = re.compile(r"\(d:(?P<format>[^)]+)\)")

# macOS calls the videos folder "Movies"; everywhere else it's "Videos".
_VIDEOS_DIR = Path.home() / ("Movies" if sys.platform == "darwin" else "Videos")


def generate_output_path(
    input_path: str,
    output_type: str,
    template: str = "(p)(f)",
    number_index: int = 0,
    number_max: int = 1,
) -> str:
    input_path = os.path.abspath(input_path)
    input_ext = Path(input_path).suffix.lstrip(".")
    input_no_ext = input_path[: -(len(input_ext) + 1)] if input_ext else input_path
    output_ext = output_type.lower()

    if not template:
        return f"{input_no_ext}.{output_ext}"

    filename = os.path.basename(input_no_ext)
    parent_dir = os.path.dirname(input_no_ext)
    if not parent_dir.endswith(os.sep):
        parent_dir += os.sep

    directories = parent_dir.rstrip(os.sep).split(os.sep)

    out = template
    out = out.replace("(path)", parent_dir).replace("(p)", parent_dir)
    out = out.replace("(filename)", filename).replace("(f)", filename)
    out = out.replace("(F)", filename.upper())
    out = out.replace("(outputext)", output_ext).replace("(o)", output_ext)
    out = out.replace("(O)", output_ext.upper())
    out = out.replace("(inputext)", input_ext).replace("(i)", input_ext)
    out = out.replace("(I)", input_ext.upper())

    # Special path variables
    out = out.replace("(p:d)", str(Path.home() / "Documents") + os.sep)
    out = out.replace("(p:documents)", str(Path.home() / "Documents") + os.sep)
    out = out.replace("(p:m)", str(Path.home() / "Music") + os.sep)
    out = out.replace("(p:music)", str(Path.home() / "Music") + os.sep)
    out = out.replace("(p:v)", str(_VIDEOS_DIR) + os.sep)
    out = out.replace("(p:videos)", str(_VIDEOS_DIR) + os.sep)
    out = out.replace("(p:p)", str(Path.home() / "Pictures") + os.sep)
    out = out.replace("(p:pictures)", str(Path.home() / "Pictures") + os.sep)

    # Directory hierarchy variables
    for idx, d in enumerate(directories):
        level = len(directories) - idx - 1
        out = out.replace(f"(d{level})", d)
        out = out.replace(f"(D{level})", d.upper())

    # Number variables
    out = out.replace("(n:i)", str(number_index))
    out = out.replace("(n:c)", str(number_max))

    # Date variables
    def _date_replace(m):
        fmt = m.group("format")
        return datetime.now().strftime(fmt).replace("/", "-").replace(":", "'")
    out = _DATE_RE.sub(_date_replace, out)

    out += f".{output_ext}"
    return out


# Every output path claimed by any job in this process. Checking os.path.exists
# alone is not enough: jobs are prepared concurrently, so two of them (a.jpg
# and a.gif, both converting to a.png) would each see a free path and claim the
# same one — silently overwriting each other's output, and, with
# input_post_action=delete, destroying both originals.
_claimed_paths: set[str] = set()
_claim_lock = threading.Lock()


def generate_unique_path(path: str, reserved: set[str] | None = None) -> str:
    """Return a path that collides with neither an existing file, nor a path
    claimed by another job in this process, nor one already in `reserved`
    (the outputs of this same job, e.g. one image per PDF page).

    The returned path is claimed process-wide until release_path() frees it.
    """
    extra = reserved or set()
    with _claim_lock:
        candidate = path
        counter = 2
        while (os.path.exists(candidate)
               or candidate in _claimed_paths
               or candidate in extra):
            base, ext = os.path.splitext(path)
            candidate = f"{base} ({counter}){ext}"
            counter += 1
        _claimed_paths.add(candidate)
        return candidate


def release_path(path: str) -> None:
    """Give up a claim (the job failed and removed its output)."""
    with _claim_lock:
        _claimed_paths.discard(path)

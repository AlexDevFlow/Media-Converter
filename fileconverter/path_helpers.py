"""Output path generation — ported from PathHelpers.cs."""

from __future__ import annotations
import os
import re
from datetime import datetime
from pathlib import Path

_DATE_RE = re.compile(r"\(d:(?P<format>[^)]+)\)")


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
    out = out.replace("(p:v)", str(Path.home() / "Videos") + os.sep)
    out = out.replace("(p:videos)", str(Path.home() / "Videos") + os.sep)
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


def generate_unique_path(path: str, reserved: set[str] | None = None) -> str:
    """Return a path that collides with neither an existing file nor a path
    already claimed in `reserved` (used when generating a batch of outputs in
    one prepare() pass, before any of them exist on disk)."""
    reserved = reserved or set()
    if not os.path.exists(path) and path not in reserved:
        return path
    base, ext = os.path.splitext(path)
    counter = 2
    while True:
        candidate = f"{base} ({counter}){ext}"
        if not os.path.exists(candidate) and candidate not in reserved:
            return candidate
        counter += 1

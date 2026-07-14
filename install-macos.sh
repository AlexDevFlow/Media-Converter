#!/bin/bash
# File Converter for macOS — installer
#
# Installs the tool into ~/.local/share/fileconverter (payload + private
# venv), then hands off to `fileconverter --install`, which checks the
# media tools, writes the launchers and generates the Finder Quick Actions.
#
# A private venv from source — rather than a prebuilt binary — is deliberate:
# the Linux prebuilt binary broke against rolling-release system libraries
# (GH #6) and tripped "not authorized to execute" policies (GH #5).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_DIR="$HOME/.local/share/fileconverter"
PAYLOAD="$APP_DIR/app"
VENV="$APP_DIR/venv"

echo ""
echo "=== File Converter for macOS — Install ==="
echo ""

# ── 1. Pick a Python ──
# The main UI is native SwiftUI (compiled during setup); tkinter is only the
# fallback. Still, prefer the interpreter with the NEWEST Tk: Apple's bundled
# Tk 8.5 draws blank windows on recent macOS, while Homebrew's python-tk
# ships a current Tk.
PYTHON=""
BEST_TK="0"
CANDIDATES=("/usr/bin/python3")
if command -v brew >/dev/null 2>&1; then
    BREW_PREFIX="$(brew --prefix 2>/dev/null || true)"
    [ -n "$BREW_PREFIX" ] && CANDIDATES+=("$BREW_PREFIX/bin/python3")
fi
if OTHER="$(command -v python3 2>/dev/null)"; then
    CANDIDATES+=("$OTHER")
fi

for cand in "${CANDIDATES[@]}"; do
    [ -n "$cand" ] && [ -x "$cand" ] || continue
    "$cand" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' 2>/dev/null || continue
    TK_VER="$("$cand" -c 'import tkinter; print(tkinter.TkVersion)' 2>/dev/null || echo 0)"

    # Take the first usable candidate, then only trade up for a strictly newer
    # Tk. A Python WITHOUT tkinter (TK_VER=0) is still perfectly usable — the
    # main UI is the native SwiftUI one — so it must not be rejected.
    if [ -z "$PYTHON" ]; then
        PYTHON="$cand"
        BEST_TK="$TK_VER"
    elif [ "$TK_VER" != "$BEST_TK" ] \
         && [ "$(printf '%s\n%s\n' "$BEST_TK" "$TK_VER" | sort -g | tail -1)" = "$TK_VER" ]; then
        PYTHON="$cand"
        BEST_TK="$TK_VER"
    fi
done

if [ -z "$PYTHON" ]; then
    echo "Python 3.9+ not found. Install the Xcode Command Line Tools first:"
    echo "  xcode-select --install"
    exit 1
fi
if [ "$BEST_TK" = "0" ]; then
    echo "note: no tkinter found — GUI falls back to the native SwiftUI front-end"
    echo "      only (built during setup if the Command Line Tools are present)."
fi
echo "Using Python: $PYTHON ($("$PYTHON" -c 'import platform; print(platform.python_version())'), Tk $BEST_TK)"

# ── 2. Copy the payload ──
mkdir -p "$PAYLOAD"
# resources/ and locales/ live inside the package now
rsync -a --delete "$SCRIPT_DIR/fileconverter" "$PAYLOAD/"

# ── 3. Private venv with PyYAML (rebuilt if the chosen Python changed) ──
MARKER="$APP_DIR/.venv-python"
if [ -x "$VENV/bin/python3" ]; then
    RECORDED="$( [ -f "$MARKER" ] && cat "$MARKER" || echo "unknown" )"
    if [ "$RECORDED" != "$PYTHON" ]; then
        echo "Python changed ($RECORDED → $PYTHON) — rebuilding venv..."
        rm -rf "$VENV"
    fi
fi
if [ ! -x "$VENV/bin/python3" ]; then
    echo "Creating venv..."
    "$PYTHON" -m venv "$VENV"
fi
printf '%s' "$PYTHON" > "$MARKER"
"$VENV/bin/python3" -m pip install --quiet --disable-pip-version-check pyyaml

# ── 4. Hand off to the Python installer (deps, launchers, Quick Actions) ──
cd "$PAYLOAD"
exec "$VENV/bin/python3" -m fileconverter --install

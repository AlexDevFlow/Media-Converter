#!/usr/bin/env bash
# File Converter — installer
# Linux: works on any distro (Ubuntu, Fedora, Arch, openSUSE, ...).
# macOS: dispatches to install-macos.sh (Finder Quick Actions).
# Can be run from source or will use PyInstaller binary if built (Linux only).

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# macOS gets its own installer (venv + Finder Quick Actions)
if [ "$(uname -s)" = "Darwin" ]; then
    exec bash "$SCRIPT_DIR/install-macos.sh" "$@"
fi

# Check if there's a built binary
if [ -f "$SCRIPT_DIR/dist/fileconverter" ]; then
    exec "$SCRIPT_DIR/dist/fileconverter" --install
fi

# Otherwise run from source
if ! command -v python3 &>/dev/null; then
    echo "Python 3 is required. Please install it first."
    exit 1
fi

# Check PyYAML
if ! python3 -c "import yaml" 2>/dev/null; then
    echo "Installing PyYAML..."
    if command -v apt &>/dev/null; then
        sudo apt install -y python3-yaml 2>/dev/null || true
    elif command -v dnf &>/dev/null; then
        sudo dnf install -y python3-pyyaml 2>/dev/null || true
    elif command -v pacman &>/dev/null; then
        sudo pacman -S --noconfirm python-yaml 2>/dev/null || true
    elif command -v zypper &>/dev/null; then
        sudo zypper install -y python3-PyYAML 2>/dev/null || true
    fi
    # Final fallback
    if ! python3 -c "import yaml" 2>/dev/null; then
        pip3 install --user pyyaml 2>/dev/null || pip3 install --user --break-system-packages pyyaml 2>/dev/null || true
    fi
fi

cd "$SCRIPT_DIR"
PYTHONPATH="$SCRIPT_DIR:$PYTHONPATH" exec python3 -m fileconverter --install

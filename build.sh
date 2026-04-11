#!/usr/bin/env bash
# Build a single-file executable using PyInstaller
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

GREEN='\033[0;32m'
RED='\033[0;31m'
BOLD='\033[1m'
NC='\033[0m'

echo -e "${BOLD}=== Building File Converter binary ===${NC}\n"

# Check PyInstaller
if ! python3 -c "import PyInstaller" 2>/dev/null; then
    echo -e "${RED}PyInstaller not found. Installing...${NC}"
    pip3 install --user pyinstaller 2>/dev/null || pip3 install --user --break-system-packages pyinstaller
fi

# Build
echo -e "Building with PyInstaller..."
python3 -m PyInstaller fileconverter.spec --noconfirm --clean 2>&1 | tail -5

if [ -f "dist/fileconverter" ]; then
    SIZE=$(du -sh dist/fileconverter | cut -f1)
    echo -e "\n${GREEN}${BOLD}Build successful!${NC}"
    echo -e "${GREEN}Binary: dist/fileconverter ($SIZE)${NC}"
    echo ""
    echo "To use:"
    echo "  ./dist/fileconverter              # First run: auto-setup"
    echo "  ./dist/fileconverter --install     # Re-run setup"
    echo "  ./dist/fileconverter --uninstall   # Remove integration"
else
    echo -e "\n${RED}Build failed!${NC}"
    exit 1
fi

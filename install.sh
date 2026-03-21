#!/usr/bin/env bash
# install.sh — StormShell installer
# ────────────────────────────────────────────────
# One-line install:
#   curl -sSL https://raw.githubusercontent.com/HorseyofCoursey/stormshell/main/install.sh | sudo bash

set -euo pipefail

REPO_URL="https://github.com/HorseyofCoursey/stormshell.git"
INSTALL_DIR="/home/pi/stormshell"
SCRIPT="stormshell.py"
LOCATION="London"

# Allow passing location as argument
while [[ $# -gt 0 ]]; do
    case "$1" in
        --location) LOCATION="$2"; shift 2 ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

echo ""
echo "+---------------------------------------+"
echo "|   StormShell  ☼  Installer            |"
echo "+---------------------------------------+"
echo ""

# Ask for location — works both interactively and when piped via curl
exec 3</dev/tty
read -rp "  Your location (city or postal code) [$LOCATION]: " i <&3
LOCATION="${i:-$LOCATION}"
exec 3>&-
echo ""

echo "  Checking Python 3..."
python3 --version || { echo "ERROR: python3 not found"; exit 1; }

if ! command -v git &>/dev/null; then
    echo "  Installing git..."
    apt-get install -y git > /dev/null
fi

# Clone or update
if [[ -d "$INSTALL_DIR/.git" ]]; then
    echo "  Updating existing install..."
    PULL_OUT=$(git -C "$INSTALL_DIR" pull --ff-only)
    echo "  $PULL_OUT"
    if [[ "$PULL_OUT" != *"Already up to date"* ]]; then
        exec bash "$INSTALL_DIR/install.sh" --location "$LOCATION"
    fi
elif [[ -f "$(dirname "$0")/$SCRIPT" ]]; then
    SRC_DIR="$(cd "$(dirname "$0")" && pwd)"
    echo "  Installing from local source..."
    mkdir -p "$INSTALL_DIR"
    cp "$SRC_DIR/$SCRIPT" "$INSTALL_DIR/$SCRIPT"
else
    echo "  Cloning StormShell..."
    git clone "$REPO_URL" "$INSTALL_DIR"
fi

chmod +x "$INSTALL_DIR/$SCRIPT"

# Patch default location into script
python3 -c "
import sys, re
script, location = sys.argv[1], sys.argv[2]
src = open(script).read()
src = re.sub(r'^DEFAULT_LOCATION = .*', 'DEFAULT_LOCATION = \"' + location + '\"', src, flags=re.M)
open(script, 'w').write(src)
" "$INSTALL_DIR/$SCRIPT" "$LOCATION"

echo "  [OK] Script installed to $INSTALL_DIR"

# Create launcher
printf '#!/bin/bash\nexec python3 %s/%s --location "%s" "$@"\n' \
    "$INSTALL_DIR" "$SCRIPT" "$LOCATION" \
    > /usr/local/bin/stormshell
chmod +x /usr/local/bin/stormshell
echo "  [OK] Launcher created"

echo ""
echo "  Temperature and wind units are auto-detected from your location."
echo "  Override anytime with:  stormshell --units fahrenheit --wind mph"
echo ""
echo "  Run:      stormshell"
echo "  Preview:  stormshell --preview"
echo "  Display:  stormshell --display"
echo ""
echo "+---------------------------------------+"
echo "|  Done! Enjoy StormShell  ☼            |"
echo "+---------------------------------------+"
echo ""

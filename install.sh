#!/usr/bin/env bash
# install.sh — StormShell installer
# One-line install:
#   curl -sSL https://raw.githubusercontent.com/HorseyofCoursey/stormshell/main/install.sh | sudo bash

set -euo pipefail

REPO_URL="https://github.com/HorseyofCoursey/stormshell.git"
INSTALL_DIR="/home/pi/stormshell"
SCRIPT="stormshell.py"

echo ""
echo "+---------------------------------------+"
echo "|   StormShell  -  Installer            |"
echo "+---------------------------------------+"
echo ""

echo "  Checking Python 3..."
python3 --version || { echo "ERROR: python3 not found"; exit 1; }

if ! command -v git &>/dev/null; then
    echo "  Installing git..."
    apt-get install -y git > /dev/null
fi

if [[ -d "$INSTALL_DIR/.git" ]]; then
    echo "  Updating existing install..."
    PULL_OUT=$(git -C "$INSTALL_DIR" pull --ff-only)
    echo "  $PULL_OUT"
    if [[ "$PULL_OUT" != *"Already up to date"* ]]; then
        exec bash "$INSTALL_DIR/install.sh"
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

printf '#!/bin/bash\nexec python3 %s/%s "$@"\n' \
    "$INSTALL_DIR" "$SCRIPT" \
    > /usr/local/bin/stormshell
chmod +x /usr/local/bin/stormshell
echo "  [OK] Launcher created"

echo ""
echo "  Usage:"
echo "    stormshell --location \"London\""
echo "    stormshell --location \"10001\""
echo "    stormshell --display --location \"London\""
echo "    stormshell --preview"
echo ""
echo "+---------------------------------------+"
echo "|  Done! Enjoy StormShell               |"
echo "+---------------------------------------+"
echo ""

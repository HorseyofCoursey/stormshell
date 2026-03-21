#!/usr/bin/env bash
# install.sh — StormShell installer
# ────────────────────────────────────────────────
# One-line install:
#   curl -sSL https://raw.githubusercontent.com/HorseyofCoursey/stormshell/main/install.sh | sudo bash
#
# Or clone and run:
#   git clone https://github.com/HorseyofCoursey/stormshell.git
#   cd stormshell && sudo ./install.sh

set -euo pipefail

REPO_URL="https://github.com/HorseyofCoursey/stormshell.git"
INSTALL_DIR="/home/pi/stormshell"
SERVICE_NAME="stormshell"
SCRIPT="stormshell.py"

LOCATION="London"
COUNTRY=""
UNITS=""
WIND=""
KIOSK=false

while [[ $# -gt 0 ]]; do
    case "$1" in
        --location) LOCATION="$2"; shift 2 ;;
        --country)  COUNTRY="$2";  shift 2 ;;
        --units)    UNITS="$2";    shift 2 ;;
        --wind)     WIND="$2";     shift 2 ;;
        --kiosk)    KIOSK=true;    shift   ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

echo ""
echo "+---------------------------------------+"
echo "|   StormShell  -  Installer            |"
echo "+---------------------------------------+"
echo ""

# Read from /dev/tty directly so prompts work even when piped via curl
if ! $KIOSK; then
    exec 3</dev/tty
    read -rp "  Location (city name or postal code) [$LOCATION]: " i <&3
    LOCATION="${i:-$LOCATION}"
    read -rp "  Country code - optional (gb/de/jp/au...) [$COUNTRY]: " i <&3
    COUNTRY="${i:-$COUNTRY}"
    read -rp "  Temp units - leave blank for auto (fahrenheit/celsius) [$UNITS]: " i <&3
    UNITS="${i:-$UNITS}"
    read -rp "  Wind units - leave blank for auto (mph/kmh/ms/kn) [$WIND]: " i <&3
    WIND="${i:-$WIND}"
    read -rp "  Install as kiosk service on HDMI display? [y/N]: " i <&3
    [[ "${i,,}" == "y" ]] && KIOSK=true
    exec 3>&-
    echo ""
fi

echo "  Checking Python 3..."
python3 --version || { echo "ERROR: python3 not found"; exit 1; }
echo "  OK"

if ! command -v git &>/dev/null; then
    echo "  Installing git..."
    apt-get install -y git > /dev/null
fi

if [[ -d "$INSTALL_DIR/.git" ]]; then
    echo "  Updating existing install..."
    PULL_OUT=$(git -C "$INSTALL_DIR" pull --ff-only)
    echo "  $PULL_OUT"
    if [[ "$PULL_OUT" != *"Already up to date"* ]]; then
        exec bash "$INSTALL_DIR/install.sh" "$@"
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

python3 -c "
import sys, re
script, location, country, units, wind = sys.argv[1:]
src = open(script).read()
src = re.sub(r'^DEFAULT_LOCATION = .*', 'DEFAULT_LOCATION = \"' + location + '\"', src, flags=re.M)
src = re.sub(r'^DEFAULT_COUNTRY  = .*', 'DEFAULT_COUNTRY  = \"' + country + '\"',  src, flags=re.M)
if units: src = re.sub(r'^TEMP_UNIT        = .*', 'TEMP_UNIT        = \"' + units + '\"', src, flags=re.M)
if wind:  src = re.sub(r'^WIND_UNIT        = .*', 'WIND_UNIT        = \"' + wind  + '\"', src, flags=re.M)
open(script,'w').write(src)
" "$INSTALL_DIR/$SCRIPT" "$LOCATION" "$COUNTRY" "$UNITS" "$WIND"

echo "  [OK] Script installed to $INSTALL_DIR"

LAUNCH_ARGS="--location \"$LOCATION\""
[[ -n "$COUNTRY" ]] && LAUNCH_ARGS="$LAUNCH_ARGS --country $COUNTRY"
[[ -n "$UNITS"   ]] && LAUNCH_ARGS="$LAUNCH_ARGS --units $UNITS"
[[ -n "$WIND"    ]] && LAUNCH_ARGS="$LAUNCH_ARGS --wind $WIND"

printf '#!/bin/bash\nexec python3 %s/%s %s "$@"\n' \
    "$INSTALL_DIR" "$SCRIPT" "$LAUNCH_ARGS" \
    > /usr/local/bin/stormshell
chmod +x /usr/local/bin/stormshell
echo "  [OK] Launcher: /usr/local/bin/stormshell"

if $KIOSK; then
    echo ""
    echo "  Installing kiosk service..."

    if [[ ! -f /usr/share/consolefonts/Uni2-TerminusBold28x14.psf.gz ]]; then
        echo "  Installing console fonts..."
        apt-get install -y console-setup fonts-terminus > /dev/null
    fi

    printf '[Unit]\nDescription=StormShell weather display\nAfter=network-online.target\nWants=network-online.target\n\n[Service]\nType=simple\nUser=pi\nGroup=pi\nStandardInput=tty\nStandardOutput=tty\nTTYPath=/dev/tty1\nTTYReset=yes\nTTYVHangup=yes\nExecStartPre=/bin/sleep 5\nExecStartPre=/usr/bin/setfont /usr/share/consolefonts/Uni2-TerminusBold28x14.psf.gz\nExecStart=/usr/local/bin/stormshell\nRestart=on-failure\nRestartSec=10\n\n[Install]\nWantedBy=multi-user.target\n' \
        > "/etc/systemd/system/${SERVICE_NAME}.service"

    systemctl daemon-reload
    systemctl enable "$SERVICE_NAME"
    systemctl disable getty@tty1 2>/dev/null || true
    systemctl stop    getty@tty1 2>/dev/null || true

    echo "  [OK] Kiosk service installed and enabled"
    echo ""
    echo "  Start now:  sudo systemctl start stormshell"
    echo "  Logs:       sudo journalctl -u stormshell -f"
else
    echo ""
    echo "  Run with:   stormshell"
    echo "  Preview:    stormshell --preview"
    echo "  Display:    stormshell --display"
fi

echo ""
echo "+---------------------------------------+"
echo "|  Done! Enjoy StormShell               |"
echo "+---------------------------------------+"
echo ""

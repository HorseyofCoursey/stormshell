#!/usr/bin/env bash
# install.sh — set up StormShell on Raspberry Pi
# ──────────────────────────────────────────────────────────
# Usage:
#   chmod +x install.sh && sudo ./install.sh            # interactive
#   sudo ./install.sh --zip 60201 --kiosk               # non-interactive kiosk

set -euo pipefail

INSTALL_DIR="/home/pi/stormshell"
SERVICE_NAME="stormshell"
SCRIPT="stormshell.py"
SRC_DIR="$(cd "$(dirname "$0")" && pwd)"

# Defaults
ZIP="60201"
COUNTRY="us"
UNITS="fahrenheit"
WIND="mph"
KIOSK=false

while [[ $# -gt 0 ]]; do
    case "$1" in
        --zip)     ZIP="$2";     shift 2 ;;
        --country) COUNTRY="$2"; shift 2 ;;
        --units)   UNITS="$2";   shift 2 ;;
        --wind)    WIND="$2";    shift 2 ;;
        --kiosk)   KIOSK=true;   shift   ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

echo ""
echo "+---------------------------------------+"
echo "|  StormShell  -  Installer  |"
echo "+---------------------------------------+"
echo ""

# Interactive prompts when not in kiosk mode
if ! $KIOSK; then
    read -rp "  ZIP / postal code    [$ZIP]:      " i; ZIP="${i:-$ZIP}"
    read -rp "  Country code         [$COUNTRY]:  " i; COUNTRY="${i:-$COUNTRY}"
    read -rp "  Temp units (fahrenheit|celsius) [$UNITS]: " i; UNITS="${i:-$UNITS}"
    read -rp "  Wind units (mph|kmh|ms|kn) [$WIND]: " i; WIND="${i:-$WIND}"
    read -rp "  Install as systemd kiosk service? [y/N]: " i
    [[ "${i,,}" == "y" ]] && KIOSK=true
    echo ""
fi

# Check Python 3
echo "  Checking Python 3..."
python3 --version || { echo "ERROR: python3 not found"; exit 1; }
echo "  OK — no additional packages needed (uses stdlib only)"
echo ""

# Install files
echo "  Installing to $INSTALL_DIR ..."
mkdir -p "$INSTALL_DIR"
cp "$SRC_DIR/$SCRIPT" "$INSTALL_DIR/$SCRIPT"
chmod +x "$INSTALL_DIR/$SCRIPT"

# Patch defaults into the copy so running it bare works
sed -i \
    -e "s/^DEFAULT_ZIP     = .*/DEFAULT_ZIP     = \"$ZIP\"/" \
    -e "s/^DEFAULT_COUNTRY = .*/DEFAULT_COUNTRY = \"$COUNTRY\"/" \
    -e "s/^TEMP_UNIT       = .*/TEMP_UNIT       = \"$UNITS\"/" \
    -e "s/^WIND_UNIT       = .*/WIND_UNIT       = \"$WIND\"/" \
    "$INSTALL_DIR/$SCRIPT"

echo "  [OK] Script installed"

# Launcher shortcut
cat > /usr/local/bin/stormshell <<EOF
#!/bin/bash
exec python3 $INSTALL_DIR/$SCRIPT "\$@"
EOF
chmod +x /usr/local/bin/stormshell
echo "  [OK] Launcher: /usr/local/bin/stormshell"

# Check font for kiosk mode
if $KIOSK; then
    FONT_PATH="/usr/share/consolefonts/Uni2-TerminusBold28x14.psf.gz"
    if [[ ! -f "$FONT_PATH" ]]; then
        echo ""
        echo "  Installing console fonts (needed for ☼ ░ ▒ on TTY)..."
        apt-get install -y console-setup fonts-terminus > /dev/null
    fi
    echo "  [OK] Console font available"
fi

# Systemd kiosk service
if $KIOSK; then
    echo ""
    echo "  Installing systemd service..."

    cat > "/etc/systemd/system/${SERVICE_NAME}.service" <<EOF
[Unit]
Description=StormShell (kiosk)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=pi
Group=pi
StandardInput=tty
StandardOutput=tty
TTYPath=/dev/tty1
TTYReset=yes
TTYVHangup=yes

# Load Uni Terminus font so ☼ ░ ▒ ▓ and box-draw render on the raw TTY.
# SSH terminals handle this automatically; the bare TTY needs this one step.
ExecStartPre=/usr/bin/setfont /usr/share/consolefonts/Uni2-TerminusBold28x14.psf.gz

ExecStart=/usr/bin/python3 $INSTALL_DIR/$SCRIPT --zip $ZIP --country $COUNTRY --units $UNITS --wind $WIND
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

    systemctl daemon-reload
    systemctl enable "$SERVICE_NAME"

    # Hand TTY1 to the StormShell
    systemctl disable getty@tty1 2>/dev/null || true
    systemctl stop    getty@tty1 2>/dev/null || true

    # Hide the cursor so it doesn't blink over the art
    grep -q "setterm" /etc/rc.local 2>/dev/null || \
        sed -i '/^exit 0/i setterm --cursor off > /dev/tty1' /etc/rc.local 2>/dev/null || true

    echo "  [OK] Service installed and enabled"
    echo "  [OK] getty@tty1 disabled (TTY1 is now owned by StormShell)"
    echo ""
    echo "  Start now :  sudo systemctl start $SERVICE_NAME"
    echo "  Status    :  sudo systemctl status $SERVICE_NAME"
    echo "  Logs      :  sudo journalctl -u $SERVICE_NAME -f"
    echo "  Disable   :  sudo systemctl disable $SERVICE_NAME"
    echo "               sudo systemctl enable getty@tty1"

else
    echo ""
    echo "  +-------------------------------------------+"
    echo "  |  To run:                                  |"
    echo "  |    weather                                |"
    echo "  |    stormshell --zip $ZIP                    |"
    echo "  |                                           |"
    echo "  |  For kiosk autostart:                     |"
    echo "  |    sudo ./install.sh --kiosk              |"
    echo "  +-------------------------------------------+"
fi

echo ""
echo "+---------------------------------------+"
echo "|  Done!                                |"
echo "+---------------------------------------+"
echo ""

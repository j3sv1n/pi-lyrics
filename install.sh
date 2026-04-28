#!/usr/bin/env bash
# ============================================================
# Pi Lyrics — Raspberry Pi OS installer
# Run once as root on a fresh Raspberry Pi OS install:
#   sudo bash install.sh
# ============================================================

set -euo pipefail

SERVICE_USER="${SUDO_USER:-pi}"
if [ -z "$SERVICE_USER" ]; then
  SERVICE_USER="pi"
fi
APP_DIR="/home/$SERVICE_USER/pi-lyrics"
VENV_DIR="$APP_DIR/venv"
TMPDIR_CUSTOM="/home/$SERVICE_USER/tmp"

if [ "$(id -u)" -ne 0 ]; then
  echo "This installer must be run as root."
  echo "Use: sudo bash install.sh"
  exit 1
fi

echo "========================================"
echo "  Pi Lyrics installer"
echo "========================================"

echo ""
echo "[1/5] Installing system packages..."
apt-get update -q
apt-get install -y -q \
  python3 python3-pip python3-venv \
  python3-watchdog python3-flask python3-pygame \
  libsdl2-dev fonts-dejavu

echo ""
echo "[2/5] Creating app directory..."
mkdir -p "$APP_DIR/pdfs"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cp "$SCRIPT_DIR/display.py" "$APP_DIR/display.py"
cp "$SCRIPT_DIR/server.py" "$APP_DIR/server.py"
chown -R "$SERVICE_USER:$SERVICE_USER" "$APP_DIR"

echo ""
echo "[3/5] Creating Python virtualenv..."
rm -rf "$VENV_DIR"
sudo -u "$SERVICE_USER" python3 -m venv "$VENV_DIR" --system-site-packages

echo ""
echo "[4/5] Installing PyMuPDF and required Python packages..."
mkdir -p "$TMPDIR_CUSTOM"
chown "$SERVICE_USER:$SERVICE_USER" "$TMPDIR_CUSTOM"

sudo -u "$SERVICE_USER" TMPDIR="$TMPDIR_CUSTOM" \
  "$VENV_DIR/bin/python" -m pip install --break-system-packages --no-cache-dir "pymupdf==1.22.3" werkzeug --upgrade

rm -rf "$TMPDIR_CUSTOM"

echo ""
echo "Installation complete."
echo ""
echo "To start the web server manually:"
echo "  cd $APP_DIR && $VENV_DIR/bin/python server.py"
echo "To start the display manually:"
echo "  DISPLAY=:0 $VENV_DIR/bin/python $APP_DIR/display.py &"
echo ""
echo "To start the display with the helper script:"
echo "  bash $SCRIPT_DIR/start-display.sh"
echo "To enable optional autostart later:"
echo "  bash $SCRIPT_DIR/enable-autostart.sh"
echo "========================================"

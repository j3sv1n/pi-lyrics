#!/usr/bin/env bash
set -euo pipefail

APP_DIR="$HOME/pi-lyrics"
AUTOSTART_DIR="$HOME/.config/autostart"
AUTOSTART_FILE="$AUTOSTART_DIR/pi-lyrics.desktop"

if [ ! -d "$APP_DIR" ]; then
  echo "App directory not found: $APP_DIR"
  echo "Run the installer first: sudo bash install.sh"
  exit 1
fi

mkdir -p "$AUTOSTART_DIR"
cat > "$AUTOSTART_FILE" <<EOF
[Desktop Entry]
Type=Application
Name=Pi Lyrics
Exec=bash -c "sleep 20 && $APP_DIR/venv/bin/python $APP_DIR/display.py"
StartupNotify=false
EOF

echo "Autostart enabled."
echo "Desktop entry created: $AUTOSTART_FILE"

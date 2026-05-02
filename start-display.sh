#!/usr/bin/env bash
set -euo pipefail

APP_DIR="$HOME/pi-lyrics"
if [ ! -d "$APP_DIR" ]; then
  echo "App directory not found: $APP_DIR"
  echo "Run the installer first: sudo bash install.sh"
  exit 1
fi

cd "$APP_DIR"
echo "Starting Pi Lyrics display..."
DISPLAY=:0 "$APP_DIR/venv/bin/python" "$APP_DIR/display.py" &

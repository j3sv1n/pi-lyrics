#!/usr/bin/env bash
set -euo pipefail

APP_DIR="$HOME/pi-lyrics"
if [ ! -d "$APP_DIR" ]; then
  echo "App directory not found: $APP_DIR"
  echo "Run the installer first: sudo bash install.sh"
  exit 1
fi

cd "$APP_DIR"
echo "Starting Pi Lyrics web server..."
"$APP_DIR/venv/bin/python" "$APP_DIR/server.py"

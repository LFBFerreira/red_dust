#!/bin/bash
# Run Croissant Control Center with console output.
# Uses Red Dust Control Center/.venv (run ./setup-raspberrypi.sh once).

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_DIR="$SCRIPT_DIR/../Croissant Control Center"
VENV_PY="$SCRIPT_DIR/../Red Dust Control Center/.venv/bin/python3"

cd "$APP_DIR" || {
  echo "Could not find Croissant Control Center next to Scripts."
  exit 1
}

if [ ! -x "$VENV_PY" ]; then
  echo "Virtual environment not found at:"
  echo "  $VENV_PY"
  echo ""
  echo "Run ./setup-raspberrypi.sh in Scripts once, then try again."
  exit 1
fi

"$VENV_PY" main.py
exit "$?"

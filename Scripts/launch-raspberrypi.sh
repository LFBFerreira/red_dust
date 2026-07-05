#!/bin/bash
# Run Red Dust Control Center with console output. Uses Red Dust Control Center/.venv
#
# First time on this Pi: run ./setup-raspberrypi.sh in Scripts.
# To launch from menu/desktop: red-dust-control-center.desktop (created by setup).

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_DIR="$SCRIPT_DIR/../Red Dust Control Center"
VENV_PY="$APP_DIR/.venv/bin/python3"

cd "$APP_DIR" || {
  echo "Could not find application folder next to Scripts."
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

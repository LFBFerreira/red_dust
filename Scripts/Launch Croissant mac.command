#!/bin/bash
# Double-click this file in Finder to open Terminal and run Croissant Control Center
# with a console for log output. Uses Red Dust Control Center/.venv
#
# First time on this Mac: run "Setup venv mac.command" in Scripts.
# chmod +x "Launch Croissant mac.command" if Finder won't run it.

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_DIR="$SCRIPT_DIR/../Croissant Control Center"
VENV_PY="$SCRIPT_DIR/../Red Dust Control Center/.venv/bin/python3"

cd "$APP_DIR" || {
  echo "Could not find Croissant Control Center next to Scripts."
  read -r -p "Press Enter to close..."
  exit 1
}

if [ ! -x "$VENV_PY" ]; then
  echo "Virtual environment not found at:"
  echo "  $VENV_PY"
  echo ""
  echo "Run \"Setup venv mac.command\" in Scripts once, then try again."
  read -r -p "Press Enter to close..."
  exit 1
fi

"$VENV_PY" main.py
exit_code=$?

if [ "$exit_code" -ne 0 ]; then
  echo ""
  echo "Exited with error code $exit_code."
  read -r -p "Press Enter to close..."
fi

exit "$exit_code"

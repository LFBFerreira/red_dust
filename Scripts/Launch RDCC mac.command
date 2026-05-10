#!/bin/bash
# Double-click this file in Finder to open Terminal and run Red Dust Control Center
# with a console for log output while the app runs. Uses Red Dust Control Center/.venv
#
# First time on this Mac: run "Setup RDCC venv.command" in Scripts.
# chmod +x "Launch RDCC mac.command" if Finder won't run it.

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_DIR="$SCRIPT_DIR/../Red Dust Control Center"
VENV_PY="$APP_DIR/.venv/bin/python3"

cd "$APP_DIR" || {
  echo "Could not find application folder next to Scripts."
  read -r -p "Press Enter to close..."
  exit 1
}

if [ ! -x "$VENV_PY" ]; then
  echo "Virtual environment not found at:"
  echo "  $VENV_PY"
  echo ""
  echo "Run \"Setup RDCC venv.command\" in Scripts once, then try again."
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

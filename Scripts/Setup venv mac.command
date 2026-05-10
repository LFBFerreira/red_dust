#!/bin/bash
# One-time setup: creates Red Dust Control Center/.venv and installs dependencies
# from requirements_mac.txt. Safe to run again to refresh pip or reinstall.

set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_DIR="$SCRIPT_DIR/../Red Dust Control Center"
VENV_PY="$APP_DIR/.venv/bin/python3"

cd "$APP_DIR" || {
  echo "Could not find application folder next to Scripts."
  read -r -p "Press Enter to close..."
  exit 1
}

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 was not found. Install Python 3 and try again."
  read -r -p "Press Enter to close..."
  exit 1
fi

if [ ! -x "$VENV_PY" ]; then
  echo "Creating virtual environment..."
  python3 -m venv .venv
fi

echo "Upgrading pip..."
"$VENV_PY" -m pip install --upgrade pip

echo "Installing packages from requirements_mac.txt..."
"$VENV_PY" -m pip install -r requirements_mac.txt

echo ""
echo "Done. You can use \"Launch RDCC mac.command\" to start the app."
read -r -p "Press Enter to close..."

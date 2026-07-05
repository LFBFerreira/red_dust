#!/bin/bash
# One-time setup: creates Red Dust Control Center/.venv and installs dependencies
# from requirements_raspberrypi.txt. Target: Raspberry Pi 5 (Debian aarch64).
# Safe to run again to refresh pip or reinstall.
#
# If venv creation fails, install system packages first:
#   sudo apt install python3-venv python3-pip
#
# For the PySide6 GUI, you may also need:
#   sudo apt install libxcb-cursor0 libxkbcommon-x11-0 libegl1 libgl1 libglib2.0-0

set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_DIR="$SCRIPT_DIR/../Red Dust Control Center"
VENV_PY="$APP_DIR/.venv/bin/python3"

OS_NAME=$(grep '^PRETTY_NAME=' /etc/os-release 2>/dev/null | cut -d= -f2- | tr -d '"' || echo "unknown")
ARCH=$(uname -m)
PYTHON=$(python3 --version 2>/dev/null | awk '{print $2}' || echo "not found")
PIP=$(python3 -m pip --version 2>/dev/null | awk '{print $2}' || echo "not found")

echo "=== Target machine ==="
echo "OS: $OS_NAME"
echo "Architecture: $ARCH"
echo "Python: $PYTHON"
echo "pip: $PIP"
echo ""

if [ "$ARCH" != "aarch64" ]; then
  echo "Warning: expected aarch64 (Raspberry Pi 64-bit), got $ARCH."
  echo "Continuing anyway — wheels and system packages may differ."
  echo ""
fi

cd "$APP_DIR" || {
  echo "Could not find application folder next to Scripts."
  exit 1
}

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 was not found. Install it with: sudo apt install python3 python3-pip python3-venv"
  exit 1
fi

if ! python3 -c "import venv" 2>/dev/null; then
  echo "python3-venv is not available. Install it with:"
  echo "  sudo apt install python3-venv"
  exit 1
fi

if [ ! -x "$VENV_PY" ]; then
  echo "Creating virtual environment..."
  python3 -m venv .venv
fi

echo "Upgrading pip..."
"$VENV_PY" -m pip install --upgrade pip

echo "Installing packages from requirements_raspberrypi.txt..."
"$VENV_PY" -m pip install -r requirements_raspberrypi.txt

LAUNCH_SCRIPT="$SCRIPT_DIR/launch-raspberrypi.sh"
DESKTOP_NAME="red-dust-control-center.desktop"
DESKTOP_FILE="$SCRIPT_DIR/$DESKTOP_NAME"
chmod +x "$LAUNCH_SCRIPT"

install_launcher() {
  cat > "$DESKTOP_FILE" <<EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=Red Dust Control Center
GenericName=Seismic control
Comment=Launch Red Dust Control Center
Exec=bash "$LAUNCH_SCRIPT"
Path=$SCRIPT_DIR
Terminal=true
StartupNotify=true
Categories=Utility;Science;
Keywords=red;dust;seismic;mars;
EOF
  chmod +x "$DESKTOP_FILE"

  # Application menu (XFCE, Raspberry Pi OS, and other freedesktop desktops)
  local apps_dir="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
  mkdir -p "$apps_dir"
  cp "$DESKTOP_FILE" "$apps_dir/$DESKTOP_NAME"
  chmod +x "$apps_dir/$DESKTOP_NAME"
  echo "Installed menu launcher: $apps_dir/$DESKTOP_NAME"

  # Desktop shortcut(s) — Pi OS (xdg-user-dir) and common fallbacks
  local desktop_dir installed_desktop=0
  if command -v xdg-user-dir >/dev/null 2>&1; then
    desktop_dir=$(xdg-user-dir DESKTOP 2>/dev/null || true)
    if [ -n "$desktop_dir" ] && [ -d "$desktop_dir" ]; then
      cp "$DESKTOP_FILE" "$desktop_dir/$DESKTOP_NAME"
      chmod +x "$desktop_dir/$DESKTOP_NAME"
      echo "Installed desktop shortcut: $desktop_dir/$DESKTOP_NAME"
      installed_desktop=1
    fi
  fi
  for desktop_dir in "$HOME/Desktop" "$HOME/desktop"; do
    if [ -d "$desktop_dir" ]; then
      cp "$DESKTOP_FILE" "$desktop_dir/$DESKTOP_NAME"
      chmod +x "$desktop_dir/$DESKTOP_NAME"
      echo "Installed desktop shortcut: $desktop_dir/$DESKTOP_NAME"
      installed_desktop=1
    fi
  done
  if [ "$installed_desktop" -eq 0 ]; then
    echo "No desktop folder found — use the application menu or ./launch-raspberrypi.sh"
  fi

  if command -v gio >/dev/null 2>&1; then
    gio set "$DESKTOP_FILE" metadata::trusted true 2>/dev/null || true
    gio set "$apps_dir/$DESKTOP_NAME" metadata::trusted true 2>/dev/null || true
    for desktop_dir in $(command -v xdg-user-dir >/dev/null 2>&1 && xdg-user-dir DESKTOP 2>/dev/null) "$HOME/Desktop" "$HOME/desktop"; do
      if [ -n "$desktop_dir" ] && [ -f "$desktop_dir/$DESKTOP_NAME" ]; then
        gio set "$desktop_dir/$DESKTOP_NAME" metadata::trusted true 2>/dev/null || true
      fi
    done
  fi

  if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "$apps_dir" 2>/dev/null || true
  fi
}

echo "Installing launcher (application menu + desktop)..."
install_launcher

echo ""
echo "Done. Start the app with:"
echo "  ./launch-raspberrypi.sh"
echo "  Application menu: search for \"Red Dust Control Center\""
echo "  Desktop: red-dust-control-center.desktop (if your desktop shows icons)"

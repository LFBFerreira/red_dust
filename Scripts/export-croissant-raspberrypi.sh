#!/bin/bash
# Build a Croissant Control Center update zip for Raspberry Pi.
# Output: ../export/croissant_pi_update.zip
#
# Unzip over the existing red_dust folder on the Pi (same layout as this repo).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
EXPORT_DIR="$REPO_ROOT/export"
STAGE="$EXPORT_DIR/croissant_pi_update"
ZIP_PATH="$EXPORT_DIR/croissant_pi_update.zip"

rm -rf "$STAGE"
mkdir -p "$STAGE/Scripts" "$STAGE/Croissant Control Center"

python3 - "$REPO_ROOT" "$STAGE" <<'PY'
import os
import shutil
import sys

repo, stage = sys.argv[1], sys.argv[2]
src = os.path.join(repo, "Croissant Control Center")
dst = os.path.join(stage, "Croissant Control Center")
skip_dirs = {
    ".venv", "venv", "env", "ENV", "cache", "sessions", "__pycache__",
    ".vscode", ".idea", "build", "dist",
}
skip_names = {".DS_Store", "Thumbs.db"}
skip_ext = {".pyc", ".pyo", ".log", ".icns"}

for root, dirs, files in os.walk(src):
    dirs[:] = [d for d in dirs if d not in skip_dirs]
    rel = os.path.relpath(root, src)
    for name in files:
        if name in skip_names or os.path.splitext(name)[1] in skip_ext:
            continue
        src_file = os.path.join(root, name)
        dest_file = os.path.join(dst, rel, name) if rel != "." else os.path.join(dst, name)
        os.makedirs(os.path.dirname(dest_file), exist_ok=True)
        shutil.copy2(src_file, dest_file)

launch = os.path.join(repo, "Scripts", "launch-croissant-raspberrypi.sh")
with open(launch, "r", encoding="utf-8", newline="") as f:
    text = f.read().replace("\r\n", "\n").replace("\r", "\n")
dest_launch = os.path.join(stage, "Scripts", "launch-croissant-raspberrypi.sh")
with open(dest_launch, "w", encoding="utf-8", newline="\n") as f:
    f.write(text)
os.chmod(dest_launch, 0o755)

readme = """Croissant Control Center — Raspberry Pi update
==============================================

This zip overlays an existing red_dust folder. It does not include the
Python venv or seismic cache.

On the Pi
---------
  1. Copy croissant_pi_update.zip to the Pi.
  2. In the existing red_dust folder:

       unzip -o croissant_pi_update.zip

  3. Launch:

       cd Scripts
       chmod +x launch-croissant-raspberrypi.sh
       ./launch-croissant-raspberrypi.sh

If the venv is missing, run setup-raspberrypi.sh once (same as Dust Devil).
"""
with open(os.path.join(stage, "README-croissant-pi.txt"), "w", encoding="utf-8", newline="\n") as f:
    f.write(readme)
PY

rm -f "$ZIP_PATH"
(
  cd "$STAGE"
  zip -r "$ZIP_PATH" . -x "*.DS_Store"
) >/dev/null

echo "Wrote $ZIP_PATH"
ls -lh "$ZIP_PATH"
find "$STAGE" -type f | wc -l | awk '{print "Files in bundle:", $1}'

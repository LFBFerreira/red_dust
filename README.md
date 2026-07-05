# Red Dust Control Center

Desktop application for the **Becoming Red Dust** installation. Loads real seismic data from NASA's InSight SEIS archive, visualizes multi-channel waveforms, and streams normalized values over OSC and serial to interactive objects (sound, light, vibration).

## Features

- Fetch and cache waveform data from the PDS InSight SEIS archive
- Multi-channel waveform viewer with time-based playback, speed control, and looping
- OSC and serial output at 60 Hz to multiple configurable objects
- Per-object scaling, pin mapping, and session save/load

## Requirements

- Python 3.8 or higher
- Platform-specific dependencies in `Red Dust Control Center/requirements_*.txt`

## Installation

Scripts live in `Scripts/`. Each platform has a one-time **setup** script (creates `Red Dust Control Center/.venv`) and a **launch** script.

### Windows

1. Install [Python 3](https://www.python.org/downloads/) and ensure it is on PATH.
2. Double-click or run:
   - `Scripts\Setup venv win.bat` — first time only
   - `Scripts\Launch RDCC win.cmd` — start the app

### macOS

1. Install Python 3 (Xcode CLI tools or python.org).
2. In Terminal, or double-click the `.command` files in Finder:
   ```bash
   chmod +x Scripts/*.command
   open "Scripts/Setup venv mac.command"    # first time only
   open "Scripts/Launch RDCC mac.command"   # start the app
   ```

### Raspberry Pi (aarch64)

1. Copy the portable bundle to the Pi (see [Portable bundle](#portable-bundle) below).
2. From the extracted folder:
   ```bash
   cd Scripts
   chmod +x setup-raspberrypi.sh launch-raspberrypi.sh
   ./setup-raspberrypi.sh
   ```
3. Launch:
   - `./launch-raspberrypi.sh`, or
   - **Red Dust Control Center** in the application menu (XFCE / Raspberry Pi OS), or
   - Desktop shortcut `red-dust-control-center.desktop` if your desktop shows icons.

**Pi system packages** (if setup or the GUI fails):

```bash
sudo apt install python3-venv python3-pip
sudo apt install libxcb-cursor0 libxkbcommon-x11-0 libegl1 libgl1 libglib2.0-0
```

Use `export.bat` to build the zip — shell scripts are exported with Unix (LF) line endings. If you copy individual `.sh` files from Windows by hand and see `$'\r'` errors, run `sed -i 's/\r$//' *.sh` once in `Scripts/`.

## Portable bundle

To copy the project to another machine without git, `.venv`, or cached data:

```powershell
.\export.bat
```

This writes `export/red_dust.zip` (~0.1 MB). Extract on the target machine; the zip contents sit at the top level (`Scripts/`, `Red Dust Control Center/`, etc.). See `README-install.txt` in the bundle for a quick reference.

## Scripts reference

| Platform | Setup | Launch |
|----------|-------|--------|
| Windows | `Scripts/Setup venv win.bat` | `Scripts/Launch RDCC win.cmd` |
| macOS | `Scripts/Setup venv mac.command` | `Scripts/Launch RDCC mac.command` |
| Raspberry Pi | `Scripts/setup-raspberrypi.sh` | `Scripts/launch-raspberrypi.sh` |

Export (repo only): `export.bat` or `Scripts/Export RDCC.ps1`

## Project layout

```
red_dust/
  Red Dust Control Center/   Application source
    core/                    Data, playback, OSC/serial
    ui/                      Desktop UI
    cache/                   Downloaded seismic data (created at runtime)
    sessions/                Saved sessions (created at runtime)
  Scripts/                   Setup, launch, and export scripts
  Interactive Object/        Firmware for physical objects (separate)
```

More detail on waveform units and data sources: `Red Dust Control Center/README.md`

## Data sources

NASA PDS InSight SEIS archive: https://pds-geosciences.wustl.edu/insight/urn-nasa-pds-insight_seis/data/

## License

See [LICENSE](LICENSE).

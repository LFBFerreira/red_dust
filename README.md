# Red Dust

Software for the **Becoming Red Dust** installation.

**Red Dust Control Center (RDCC)** is a desktop app that loads real Mars seismic data from NASA’s InSight SEIS archive, shows multi-channel waveforms, and streams normalized levels over **USB Serial** and/or **OSC** to physical **interactive objects** (shakers, lights, and similar hardware).

You do **not** need to understand every folder to get started. Most people only need the desktop app first; firmware is a separate step when you have a board.

---

## What’s in this repo

| Folder | What it is |
|--------|------------|
| `Red Dust Control Center/` | Main desktop app (Python) — waveforms, streaming, Dust Devil story timeline |
| `Croissant Control Center/` | Separate two-station app (shares the RDCC `.venv`) |
| `Scripts/` | Double-click / run scripts to set up and start the apps |
| `Interactive Object/` | Firmware for physical devices (Arduino / PlatformIO) |

Deeper notes for the main app: [Red Dust Control Center/README.md](Red%20Dust%20Control%20Center/README.md) · Croissant: [Croissant Control Center/README.md](Croissant%20Control%20Center/README.md)

---

## Quick start — desktop app (RDCC)

### What you need

1. A computer with **Windows**, **macOS**, or a **Raspberry Pi** (64-bit).
2. **Python 3.8 or newer** installed.
   - Windows: download from [python.org](https://www.python.org/downloads/) and, during setup, tick **“Add python.exe to PATH”**.
   - macOS: python.org installer, or Xcode Command Line Tools.
3. An internet connection the first time you download seismic data (later runs can use the local cache).

You do **not** need to install Python packages by hand. The setup script creates a private environment (`.venv`) inside `Red Dust Control Center/`.

### Windows (typical)

1. Open the `Scripts` folder in File Explorer.
2. **First time only:** double-click `Setup venv win.bat` and wait until it finishes (it may ask you to press a key at the end).
3. Double-click `Launch RDCC win.cmd` to start the app. A console window stays open for logs; that is normal.

If setup says Python was not found, install Python (with PATH enabled), close and reopen the scripts folder, and run setup again.

### macOS

1. In Terminal, once, make the scripts executable:
   ```bash
   chmod +x Scripts/*.command
   ```
2. **First time only:** double-click `Scripts/Setup venv mac.command` (or open it from Terminal).
3. Double-click `Scripts/Launch RDCC mac.command` to start the app.

### Raspberry Pi

Prefer the **portable zip** on the Pi (see [Portable bundle](#portable-bundle--copy-to-another-machine) below), then:

```bash
cd Scripts
chmod +x setup-raspberrypi.sh launch-raspberrypi.sh
./setup-raspberrypi.sh    # first time only
./launch-raspberrypi.sh
```

You can also use the **Red Dust Control Center** entry in the application menu after setup, if it appears.

If the GUI fails to start, install system packages:

```bash
sudo apt install python3-venv python3-pip
sudo apt install libxcb-cursor0 libxkbcommon-x11-0 libegl1 libgl1 libglib2.0-0
```

### After the app opens — a simple first run

1. Pick a station / date in the data picker and load waveforms (they cache under `Red Dust Control Center/cache/`).
2. Select channels and press play to scrub the data in the waveform viewer.
3. When you have hardware ready, add an **OSC** or **Serial** object, map channels to **Pin_A … Pin_F**, enable streaming, and play again.

Sessions can be saved under `Red Dust Control Center/sessions/` so you can reopen a setup later.

---

## Interactive objects (hardware)

The desktop app talks to boards that run firmware under `Interactive Object/`. Start the app first; then flash a device when you are ready.

| Project | Role | Setup guide |
|---------|------|-------------|
| `Interactive Object/Lilygo/lilygo_shaker/` | Main tactile / shaker firmware (Serial + OSC, Pin_A…F) | [lilygo_shaker README](Interactive%20Object/Lilygo/lilygo_shaker/README.md) |
| `Interactive Object/Lilygo/dust_devil/` | Dust Devil object (PWM + DY-HV20T play/stop for the RDCC story panel) | [dust_devil README](Interactive%20Object/Lilygo/dust_devil/README.md) |
| `Interactive Object/Lilygo/croissant/` | Croissant station boards (one sketch, `STATION_ID` 1 or 2) | [croissant README](Interactive%20Object/Lilygo/croissant/README.md) |
| `Interactive Object/Test ESP_RGB/` | Test RGB LED object (PlatformIO or Arduino) | [Test ESP_RGB README](Interactive%20Object/Test%20ESP_RGB/README.md) |
| `Interactive Object/Test Vibration Motor/` | Small vibration-motor test sketch | Open the `.ino` in that folder |

**Typical flow with a shaker board**

1. Follow the [lilygo_shaker README](Interactive%20Object/Lilygo/lilygo_shaker/README.md): install Arduino + ESP32 support, set board options in `settings.h`, upload.
2. In RDCC, create a **Serial** object (COM port, baud **115200**) and/or an **OSC** object (board IP, port/path from `settings.h`).
3. Map waveform channels to pins, enable streaming, start playback.
4. Close the Arduino Serial Monitor while RDCC uses the USB port — only one program can own it.

Wire format, WiFi (`Red_Dust_Object` AP), and troubleshooting live in the firmware README above — use that page as the source of truth for the device side.

---

## Scripts cheat sheet

| Platform | First-time setup | Start RDCC | Start Croissant |
|----------|------------------|------------|-----------------|
| Windows | `Scripts/Setup venv win.bat` | `Scripts/Launch RDCC win.cmd` | `Scripts/Launch Croissant win.cmd` |
| macOS | `Scripts/Setup venv mac.command` | `Scripts/Launch RDCC mac.command` | `Scripts/Launch Croissant mac.command` |
| Raspberry Pi | `Scripts/setup-raspberrypi.sh` | `Scripts/launch-raspberrypi.sh` | `Scripts/launch-croissant-raspberrypi.sh` |

Export a clean copy for another machine (from the repo on Windows): `export.bat` or `Scripts/Export RDCC.ps1`

---

## Project layout

```
red_dust/
  README.md                      ← you are here
  Red Dust Control Center/       Main desktop app (+ Dust Devil story timeline)
    main.py                      App entry point
    settings.py                  Defaults (ports, baud, pin slots, UI, story)
    core/                        Data, playback, OSC / serial, story clock
    ui/                          Windows and widgets
    cache/                       Downloaded seismic data (created at runtime)
    sessions/                    Saved sessions (created at runtime)
    .venv/                       Private Python env (shared with Croissant)
  Croissant Control Center/      Two-station Croissant app
  Scripts/                       Setup, launch, export
  Interactive Object/            Device firmware (separate from the desktop apps)
    Lilygo/lilygo_shaker/        Shaker / tactile object
    Lilygo/dust_devil/           Dust Devil + DY-HV20T
    Lilygo/croissant/            Croissant station firmware
    Test ESP_RGB/                RGB LED test object
    Test Vibration Motor/        Simple motor test
```

---

## Where to read next

| If you want to… | Open |
|-----------------|------|
| Understand app folders / data cache | [Red Dust Control Center/README.md](Red%20Dust%20Control%20Center/README.md) |
| Run the two-station Croissant app | [Croissant Control Center/README.md](Croissant%20Control%20Center/README.md) |
| Flash and wire the shaker board | [Interactive Object/Lilygo/lilygo_shaker/README.md](Interactive%20Object/Lilygo/lilygo_shaker/README.md) |
| Flash Dust Devil / Croissant boards | [dust_devil](Interactive%20Object/Lilygo/dust_devil/README.md) · [croissant](Interactive%20Object/Lilygo/croissant/README.md) |
| Build the RGB LED test object | [Interactive Object/Test ESP_RGB/README.md](Interactive%20Object/Test%20ESP_RGB/README.md) |
| Browse raw InSight SEIS files | [NASA PDS InSight SEIS archive](https://pds-geosciences.wustl.edu/insight/urn-nasa-pds-insight_seis/data/) |

---

## Portable bundle — copy to another machine

To ship the project **without** git history, `.venv`, or cached waveforms:

```powershell
.\export.bat
```

This writes `export/red_dust.zip`. Extract it on the other computer, then run that platform’s **setup** script once and **launch** as above.

If you copy `.sh` scripts from Windows by hand and see `$'\r'` errors on the Pi, fix line endings once in `Scripts/`:

```bash
sed -i 's/\r$//' *.sh
```

(Using `export.bat` avoids that for the zip.)

---

## Data sources

NASA PDS InSight SEIS archive:  
https://pds-geosciences.wustl.edu/insight/urn-nasa-pds-insight_seis/data/

---

## License

See [LICENSE](LICENSE).

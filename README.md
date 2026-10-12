# Red Dust

Software and firmware for the **Becoming Red Dust** installation.

The repo has **two desktop apps** and several **device firmware** projects. They share the same idea: load real Mars seismic data (NASA InSight SEIS), play it back, and stream normalized levels (0…1) over **USB Serial** and/or **OSC** to physical objects.

You do **not** need every sub-project. Start with **Red Dust Control Center**; add hardware and the other apps when you need them.

---

## Sub-projects at a glance

### Desktop apps

| Project | What it does | When to use it |
|---------|--------------|----------------|
| **[Red Dust Control Center](Red%20Dust%20Control%20Center/)** (RDCC) | Main control app: fetch/cache waveforms, multi-channel playback, map channels to pins, stream to objects. Includes the **Dust Devil** story timeline (clip lanes, pin gating, play/stop toward the board). | Day-to-day control of the installation and Dust Devil. |
| **[Croissant Control Center](Croissant%20Control%20Center/)** | Separate app for **Croissant**: two stations on one Pi, each with its own story clock, Play/Stop, and board. Waveform playback stays global; object cards bind to Station 1 or 2. Shares RDCC’s `.venv`. | Only when running the two-station Croissant setup. |

Setup and launch for both apps: [Quick start](#quick-start--install-and-run) · Scripts table below.

More detail: [RDCC README](Red%20Dust%20Control%20Center/README.md) · [Croissant README](Croissant%20Control%20Center/README.md)

### Firmware (`Interactive Object/`)

Pair each sketch with the matching app. Flash with Arduino (or PlatformIO where noted); configure pins and paths in that folder’s `settings.h` / README.

| Project | Talks to | Role |
|---------|----------|------|
| **[lilygo_shaker](Interactive%20Object/Lilygo/lilygo_shaker/)** | RDCC | General tactile / shaker object (Serial + OSC, Pin_A…F). PCM5102 I2S or PWM+RC output; ESP32-S3 or TTGO T-Display. |
| **[dust_devil](Interactive%20Object/Lilygo/dust_devil/)** | RDCC Dust Devil panel | Six PWM tactile channels + **DY-HV20T** amp play/stop. Story timing lives in RDCC; the board plays the live stream. |
| **[croissant](Interactive%20Object/Lilygo/croissant/)** | Croissant Control Center | One board per station (`STATION_ID` 1 or 2). Pin_A/B motors + DY-HV20T; OSC paths `/red_dust/croissant/1` and `/2`. |
| **[dy_hv20t_play_stop](Interactive%20Object/Lilygo/dy_hv20t_play_stop/)** | — | Small helper sketch to test DY-HV20T play/stop wiring on its own. |
| **[Archive](Interactive%20Object/Archive/)** | — | Older experiments: `Test ESP_RGB/` (RGB LED over Serial/OSC), `vibration/` (simple motor test). Kept for reference, not the main path. |

---

## How the pieces connect

```text
  InSight SEIS data
         │
         ▼
  ┌─────────────────────┐         Serial / OSC          ┌──────────────────┐
  │ Red Dust Control    │ ─────────────────────────────►│ lilygo_shaker    │
  │ Center (RDCC)       │                               └──────────────────┘
  │  + Dust Devil panel │ ─────────────────────────────►│ dust_devil       │
  └─────────────────────┘                               └──────────────────┘

  ┌─────────────────────┐         Serial / OSC          ┌──────────────────┐
  │ Croissant Control   │ ── Station 1 ───────────────►│ croissant (ID 1) │
  │ Center              │ ── Station 2 ───────────────►│ croissant (ID 2) │
  └─────────────────────┘                               └──────────────────┘
```

Typical order: install and learn **RDCC** → flash **lilygo_shaker** or **dust_devil** when you have hardware → use **Croissant** + two **croissant** boards only for that piece.

---

## Quick start — install and run

### What you need

1. **Windows**, **macOS**, or a **Raspberry Pi** (64-bit).
2. **Python 3.8 or newer**.
   - Windows: [python.org](https://www.python.org/downloads/) — tick **“Add python.exe to PATH”**.
   - macOS: python.org installer, or Xcode Command Line Tools.
3. Internet the first time you download seismic data (later runs can use the local cache).

You do **not** install Python packages by hand. One setup script creates `Red Dust Control Center/.venv` (used by RDCC and Croissant).

### Windows

1. Open the `Scripts` folder.
2. **First time only:** double-click `Setup venv win.bat` and wait until it finishes.
3. Double-click `Launch RDCC win.cmd` (or `Launch Croissant win.cmd`). A console window for logs is normal.

If setup says Python was not found, install Python with PATH enabled, then run setup again.

### macOS

```bash
chmod +x Scripts/*.command
```

Then double-click `Scripts/Setup venv mac.command` once, and `Scripts/Launch RDCC mac.command` (or Launch Croissant) to start.

### Raspberry Pi

Prefer the [portable zip](#portable-bundle--copy-to-another-machine), then:

```bash
cd Scripts
chmod +x setup-raspberrypi.sh launch-raspberrypi.sh launch-croissant-raspberrypi.sh
./setup-raspberrypi.sh    # first time only
./launch-raspberrypi.sh   # or ./launch-croissant-raspberrypi.sh
```

If the GUI fails:

```bash
sudo apt install python3-venv python3-pip
sudo apt install libxcb-cursor0 libxkbcommon-x11-0 libegl1 libgl1 libglib2.0-0
```

### First run in RDCC

1. Pick a station / date and load waveforms (cached under `Red Dust Control Center/cache/`).
2. Select channels and press play.
3. With a board ready: add a **Serial** or **OSC** object, map channels to pins, enable streaming, play again.
4. For Dust Devil: use the story timeline in RDCC, stream to a board running **dust_devil**, then press Play on the panel/board.

Sessions save under `Red Dust Control Center/sessions/` (Croissant keeps its own sessions).

### Scripts cheat sheet

| Platform | First-time setup | Start RDCC | Start Croissant |
|----------|------------------|------------|-----------------|
| Windows | `Scripts/Setup venv win.bat` | `Scripts/Launch RDCC win.cmd` | `Scripts/Launch Croissant win.cmd` |
| macOS | `Scripts/Setup venv mac.command` | `Scripts/Launch RDCC mac.command` | `Scripts/Launch Croissant mac.command` |
| Raspberry Pi | `Scripts/setup-raspberrypi.sh` | `Scripts/launch-raspberrypi.sh` | `Scripts/launch-croissant-raspberrypi.sh` |

Export a clean copy (Windows): `export.bat` or `Scripts/Export RDCC.ps1`

---

## Flashing hardware (short)

1. Install [Arduino IDE](https://www.arduino.cc/en/software) + ESP32 board support (details in each firmware README).
2. Open the `.ino` for the object you need (`lilygo_shaker`, `dust_devil`, or `croissant`).
3. Edit `settings.h` (board, OSC path/port, `STATION_ID` for Croissant).
4. Upload. Close Serial Monitor while RDCC/Croissant uses the USB port.

Baud default is **115200**. Full wiring, WiFi AP names, and troubleshooting: the firmware README for that folder.

---

## Project layout

```
red_dust/
  README.md                         ← you are here
  Red Dust Control Center/          Main app + Dust Devil story timeline
    .venv/                          Shared Python env (created by setup scripts)
  Croissant Control Center/         Two-station Croissant app
  Scripts/                          Setup, launch, export
  Interactive Object/
    Lilygo/lilygo_shaker/           General shaker / tactile firmware
    Lilygo/dust_devil/              Dust Devil + DY-HV20T
    Lilygo/croissant/               Croissant station firmware
    Lilygo/dy_hv20t_play_stop/      DY module wiring test
    Archive/                        Old test sketches (ESP_RGB, vibration motor)
```

---

## Where to read next

| If you want to… | Open |
|-----------------|------|
| RDCC folders / data cache | [Red Dust Control Center/README.md](Red%20Dust%20Control%20Center/README.md) |
| Run Croissant (two stations) | [Croissant Control Center/README.md](Croissant%20Control%20Center/README.md) |
| Flash the general shaker | [lilygo_shaker README](Interactive%20Object/Lilygo/lilygo_shaker/README.md) |
| Flash Dust Devil | [dust_devil README](Interactive%20Object/Lilygo/dust_devil/README.md) |
| Flash Croissant boards | [croissant README](Interactive%20Object/Lilygo/croissant/README.md) |
| Browse archived tests | [Interactive Object/Archive/](Interactive%20Object/Archive/) |
| Raw InSight SEIS files | [NASA PDS archive](https://pds-geosciences.wustl.edu/insight/urn-nasa-pds-insight_seis/data/) |

---

## Portable bundle — copy to another machine

To ship **without** git history, `.venv`, or cached waveforms:

```powershell
.\export.bat
```

This writes `export/red_dust.zip`. Extract on the other computer, then run that platform’s **setup** once and **launch**.

If hand-copied `.sh` files show `$'\r'` errors on the Pi:

```bash
sed -i 's/\r$//' Scripts/*.sh
```

(`export.bat` already uses Unix line endings for shell scripts in the zip.)

---

## Data sources

NASA PDS InSight SEIS archive:  
https://pds-geosciences.wustl.edu/insight/urn-nasa-pds-insight_seis/data/

---

## License

See [LICENSE](LICENSE).

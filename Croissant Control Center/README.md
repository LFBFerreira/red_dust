# Croissant Control Center

Desktop app for **Croissant**: two independent stations, **two LilyGO T-Display boards**, one Raspberry Pi.

This is a separate copy of Red Dust Control Center. Dust Devil / the original RDCC are unchanged.

## Difference from RDCC

- Two story clocks (each board has Pin_A/B on GPIO 25/26)
- Each station has its own Play/Stop, clips, and DY-HV20T
- Seismic waveform playback stays global
- Serial commands are `DY,PLAY` / `DY,STOP` (same as Dust Devil), sent only to that station's USB port
- Bind each object card to Station 1 or Station 2
- QSettings and sessions are stored separately (`Croissant Control Center`)

Firmware: `Interactive Object/Lilygo/croissant/` (`STATION_ID` 1 or 2 per board).

## Launch

Uses the same virtualenv as Red Dust Control Center (run `Scripts/Setup venv …` once).

| Platform | Launch |
|----------|--------|
| macOS | `Scripts/Launch Croissant mac.command` |
| Windows | `Scripts/Launch Croissant win.cmd` |
| Raspberry Pi | `Scripts/launch-croissant-raspberrypi.sh` |

Or from this folder, with the RDCC venv:

```bash
"../Red Dust Control Center/.venv/bin/python3" main.py
```

## Object cards

Add **two Serial** objects (two USB ports) or two OSC objects.

1. Set **Station** to 1 on the first card, 2 on the second
2. OSC paths: `/red_dust/croissant/1` and `/red_dust/croissant/2`
3. On each card, map channels to **Pin_A** and **Pin_B**
4. Start streaming on both, then press that station's Play

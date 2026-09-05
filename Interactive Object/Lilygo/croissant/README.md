# Croissant

LilyGO T-Display firmware for **Croissant Control Center**: **one board per station**. Both boards use the same GPIOs. Dust Devil / lilygo_vibration are unchanged.

## Two boards

Set `STATION_ID` in `settings.h` before each upload:

| Board | `STATION_ID` | OSC path | WiFi AP (first setup) |
|-------|--------------|----------|------------------------|
| Station 1 | **1** | `/red_dust/croissant/1` | `Red_Dust_Croissant1` |
| Station 2 | **2** | `/red_dust/croissant/2` | `Red_Dust_Croissant2` |

Wiring is identical on both T-Displays:

| Function | GPIO |
|----------|------|
| Pin_A motor | **25** |
| Pin_B motor | **26** |
| DY-HV20T TX (UART1) | **17** |
| Play button → GND | **21** |
| Stop button → GND | **22** |

DY-HV20T: UART Mode CON3=1, CON2=0, CON1=0. Each board has its own DY module and button pair.

## What Croissant Control Center does vs what this board does

| Side | Role |
|------|------|
| **Croissant Control Center** | Two story clocks, two Serial/OSC object cards (bind each to Station 1 or 2), pin gating, `DY1,PLAY` / `DY2,STOP` |
| **This firmware** | Receive 0…1 for Pin_A/B, drive two PWM outputs, gate with this board's Play/Stop |

Add two Serial objects (two USB ports) or two OSC objects. Set each card's **Station** to 1 or 2, map channels to **Pin_A** and **Pin_B**, start streaming, then press that station's Play.

## Protocol

- **Serial:** `v1,v2,timestamp\n` (this board's Pin_A/B). A 4-value frame still works: station 1 uses the first pair, station 2 the second.
- **PC → board:** `DY,PLAY` / `DY,STOP` / `DY,VOL,0-30` (same as Dust Devil). `DY1,` / `DY2,` are accepted only if they match `STATION_ID`.
- **Board → PC:** `DY,BTN,PLAY` / `DY,BTN,STOP` (Control Center maps the USB port to Station 1 or 2)
- **OSC path:** `/red_dust/croissant/1` or `/red_dust/croissant/2`

## Arduino setup

Same TFT_eSPI / T-Display setup as `../lilygo_vibration/README.md`. Open `croissant.ino`, set `STATION_ID`, upload to that board, then change `STATION_ID` and upload to the other.

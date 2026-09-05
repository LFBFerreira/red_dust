# Dust Devil

LilyGO T-Display firmware for the RDCC **Dust Devil** story timeline. It receives Pin_A…Pin_F levels from Red Dust Control Center and drives the same six PWM tactile outputs as `lilygo_vibration`.

`lilygo_vibration` is unchanged. Upload this sketch only when you want the Dust Devil object.

## What RDCC does vs what this board does

| Side | Role |
|------|------|
| **RDCC Dust Devil panel** | 14:30 story clock, six-lane clip editor, pin on/off gating, `DY,PLAY` / `DY,STOP` |
| **This firmware** | Receive 0…1 frames, drive PWM, gate amplifiers with DY Play/Stop, report physical button presses |

Pin timing is not stored on the ESP32. Draw clips in RDCC, start Serial/OSC streaming, then press Dust Devil **Play**.

## Hardware

Same wiring as `lilygo_vibration`:

| RDCC slot | ESP32 PWM GPIO |
|-----------|----------------|
| Pin_A | 25 |
| Pin_B | 26 |
| Pin_C | 27 |
| Pin_D | 32 |
| Pin_E | 33 |
| Pin_F | 13 |

Pin_E / Pin_F stay capped at 0.3 for the 5 W exciters (`TACTILE_MAX_LEVEL` in `settings.h`).

UART digital volume defaults to **30 / 30** (`DY_VOLUME` in `settings.h`). The onboard pot usually only changes the speaker amp, not the headphone jack.

DY-HV20T (UART Mode: CON3=1, CON2=0, CON1=0):

| LilyGO | DY-HV20T / button |
|--------|-------------------|
| GPIO 17 (TX) | IO1 / RXD |
| GND | GND |
| GPIO 21 | Play button → GND |
| GPIO 22 | Stop button → GND |

## Protocol

- **Serial:** `v1,v2,…,vN,timestamp\n` plus `DY,PLAY` / `DY,STOP` / `DY,VOL,0-30`
- **Device → RDCC:** physical Play/Stop buttons also print `DY,BTN,PLAY` / `DY,BTN,STOP` so the story clock follows the buttons
- **OSC path:** `/red_dust/dust_devil` (change `OSC_PATH` in `settings.h` to match the object card)
- **WiFi AP name** if not yet configured: `Red_Dust_DustDevil`

In RDCC, add a **Serial** object (USB) or an **OSC** object whose path is `/red_dust/dust_devil`, map channels to Pin_A…Pin_F, then Start streaming before you press Dust Devil Play.

## Arduino setup

Use the same TFT_eSPI / TFT_eWidget / ESP32 board setup as `../lilygo_vibration/README.md`. Open `dust_devil.ino` and upload to the T-Display.

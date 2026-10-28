# DY-HV20T Play / Stop (standalone test)

Minimal sketch for wiring checks only. It **replaces** whatever is on the board (including `lilygo_vibration`).

**Prefer the merged firmware:** upload  
`../lilygo_vibration/lilygo_vibration.ino`  
so tactile + DY Play/Stop run together (`ENABLE_DY_HV20T 1` in that project’s `settings.h`).

## Wiring (same as merged)

| LilyGO T-Display | DY-HV20T / button |
|------------------|-------------------|
| GPIO **17** (TX) | **IO1 / RXD** |
| **GND** | **GND** |
| GPIO **21** | Play → GND |
| GPIO **22** | Stop → GND |

DY: UART Mode CON3=1 CON2=0 CON1=0; VCC 6–35 V separate.

## When to use this folder

Only if you want to debug DY UART/buttons without WiFi, OSC, or tactile code.

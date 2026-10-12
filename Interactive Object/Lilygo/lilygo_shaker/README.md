# LilyGO / ESP32 Vibration Controller

ESP32 firmware for a **Red Dust interactive object**: it receives normalized quake levels (**Pin_A … Pin_F**, 0..1) from **Red Dust Control Center (RDCC)** over **USB Serial** and/or **OSC (UDP)**, and drives tactile shakers. RDCC loads InSight SEIS waveforms, maps channels to pins, and streams at ~60 Hz; this sketch is the device side of that link.

Two hardware output paths (chosen in `settings.h`):

| Path | What it drives |
|------|----------------|
| **PCM5102** (default) | Pin_A / Pin_B → I2S stereo → PCM5102 → amp (e.g. HW-104) → shakers. C–F unused for drive. |
| **PWM+RC** | Pin_A … Pin_F → PWM GPIOs + RC filter → amps → exciters |

Supported boards: **ESP32-S3-DevKitC-1** (default) and **LilyGo TTGO T-Display**.

---

## Setup

### 1. Arduino / ESP32 core

1. Install [Arduino IDE](https://www.arduino.cc/en/software) (or use the Arduino CLI).
2. Add the ESP32 board URL under **File → Preferences → Additional Boards Manager URLs**:  
   `https://raw.githubusercontent.com/espressif/arduino-esp32/gh-pages/package_esp32_index.json`
3. **Tools → Board → Boards Manager…** → install **esp32** by Espressif Systems.

### 2. Libraries

Install via **Library Manager**:

| Library | Required for |
|---------|----------------|
| **WiFiManager** (tzapu) | WiFi / OSC on both boards |
| **TFT_eSPI** (Bodmer) | TTGO T-Display UI only |
| **TFT_eWidget** (Bodmer) | TTGO T-Display graph only |

For **TTGO T-Display**, configure TFT_eSPI once:

1. Open `Documents/Arduino/libraries/TFT_eSPI/User_Setup_Select.h`
2. Comment out `#include <User_Setup.h>`
3. Uncomment `#include <User_Setups/Setup25_TTGO_T_Display.h>`

### 3. Board selection in the IDE

**ESP32-S3-DevKitC-1** (default in `settings.h`):

- **Tools → Board → ESP32 Arduino → ESP32S3 Dev Module** (or the matching S3 DevKit entry)
- Use the **UART** USB port for Serial upload/streaming
- Flash / USB CDC settings as needed for your module

**LilyGo TTGO T-Display**:

- **Tools → Board → ESP32 Arduino → LilyGo T-Display** (or ESP32 Dev Module)
- Set `ACTIVE_BOARD` to `BOARD_TTGO_T_DISPLAY` in `settings.h` before upload

### 4. Configure, compile, upload

1. Open `lilygo_shaker.ino`
2. Edit `settings.h` (board, output path, feel — see below)
3. **Verify**, then **Upload**
4. On first boot with WiFi, connect to AP **`Red_Dust_Object`** if needed and join your network (WiFiManager). OSC needs WiFi; Serial does not.

---

## Configuration (`settings.h`)

Primary knobs are at the top of the file. Recompile after changes.

### Board and output path

```cpp
#define ACTIVE_BOARD BOARD_ESP32_S3_DEVKITC_1   // or BOARD_TTGO_T_DISPLAY
#define ACTIVE_OUTPUT_PATH OUTPUT_PATH_PCM5102  // or OUTPUT_PATH_PWM_RC
```

### PCM5102 feel (I2S path)

| Define | Role |
|--------|------|
| `I2S_CARRIER_HZ_MIN` / `MAX` | OSC 0..1 → carrier Hz (default 25..50) |
| `I2S_AMP_SMOOTHING` | How fast levels ease (higher = snappier) |
| `SHAKE_LEVEL_FLOOR` | Weak non-zero levels remap into `[floor, 1]` so small quakes still move |

Exact **0** stays silent.

### PWM feel (PWM+RC path)

| Define | Role |
|--------|------|
| `PWM_TACTILE_CARRIER_HZ` | Haptic carrier under the envelope |
| `PWM_TACTILE_DRIVE` | Strength at OSC=1.0 (fidelity vs coil slap) |
| `PWM_TACTILE_SMOOTH_MS` | Tiny envelope smooth (click kill only) |
| `PWM_TACTILE_PINS[]` | GPIO per Pin_A…F (board-dependent) |

### OSC addressing

| Define | Default | Role |
|--------|---------|------|
| `OSC_PATH` | `/red_dust/osc_object_1` | Must match the object address in RDCC |
| `OSC_PORT` | `8000` | UDP listen port |
| `STREAM_IDLE_TIMEOUT_MS` | `3000` | Mute if no Serial/OSC for this long |
| `SERIAL_TIMEOUT_MS` | `1000` | Drop a partial Serial line if stalled |

Baud rate: `SERIAL_BAUDRATE` (default **115200**) — must match the Serial object in RDCC.

Pin maps, I2S pins, PWM timer settings, and similar live in the **SUPPORT / HARDWARE** section; leave those unless you change wiring.

### Quick wiring reference (PCM5102)

| PCM5102 | DevKitC-1 | TTGO T-Display |
|---------|-----------|----------------|
| BCK | GPIO 2 | GPIO 2 |
| LRCK (WS) | GPIO 17 | GPIO 17 |
| DIN | GPIO 18 | GPIO 22 |

---

## Streaming from RDCC

In RDCC: load waveforms, add an interactive object, map channels to Pin_A…Pin_F, enable streaming, then start playback.

### Serial (USB)

1. Plug the board in (DevKitC: prefer the **UART** port).
2. In RDCC, create a **Serial** object:
   - Port = the board’s COM / tty device  
   - Baud = **115200** (same as `SERIAL_BAUDRATE`)
3. Map Pin_A (and Pin_B… as needed) to waveform channels.
4. Enable streaming on that object and start playback.

**Wire format** (one line per tick):

```text
v1,v2,...,vN,timestamp
```

- Values are floats in Pin_A order; last field is an ISO8601 timestamp string.
- Active pins are **0..1**. Unused slots may be sent as a sentinel outside `[0, 1]`; this firmware ignores those.
- Optional whiteboard command: `FREQ,32` or `FREQ=32` forces a fixed carrier Hz (volume still from the stream).

Close the Arduino Serial Monitor while RDCC streams — only one app can own the port.

### OSC (WiFi / UDP)

1. Ensure the board has joined WiFi (status LED on DevKitC: red = idle, blue scales with Pin_A when live; TTGO shows IP on the status bar).
2. Note the board’s IP (TTGO UI, or your router / serial debug if enabled).
3. In RDCC, create an **OSC** object:
   - Host = board IP  
   - Port = `OSC_PORT` (default **8000**)  
   - Address = `OSC_PATH` (default `/red_dust/osc_object_1`)
4. Map pins, enable streaming, start playback.

**Wire format:** one OSC message per tick at `OSC_PATH`, typetag `,f…fs` — floats for Pin_A… then a timestamp **string** (same ordering as Serial).

Serial and OSC can both be active; either keeps the stream “live.” After `STREAM_IDLE_TIMEOUT_MS` with no packets, outputs mute.

---

## Project layout

| File | Role |
|------|------|
| `lilygo_shaker.ino` | Setup / loop, shared outputs & WiFi |
| `settings.h` | Board, path, feel, OSC/Serial config |
| `input.*` | Serial + OSC ingest |
| `ui.*` | TTGO TFT graph / DevKitC status LED |
| `helpers.*` | Parsing and small utilities |
| `i2s_audio.*` | PCM5102 I2S driver |
| `tactile_output.*` | PWM+RC tactile driver |

---

## Troubleshooting

- **No shake on PCM5102:** Confirm `ACTIVE_OUTPUT_PATH` is `OUTPUT_PATH_PCM5102`, wiring matches the pin table, and Pin_A/B are mapped and non-zero in RDCC.
- **OSC silent:** Board must be on WiFi; host/port/path must match `settings.h`; firewall must allow UDP to the board.
- **Serial silent / port busy:** Match baud rate; close Serial Monitor; use the UART USB port on dual-USB S3 boards.
- **TTGO blank display:** TFT_eSPI `Setup25_TTGO_T_Display` must be selected; backlight is GPIO 4 on that board only (not used as PWM Pin_A there).

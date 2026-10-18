#pragma once

// Configuration settings for Lilygo Vibration Controller

// =============================================================================
// BOARD SELECT
// =============================================================================
// 0 = LilyGo TTGO T-Display (classic ESP32)
// 1 = ESP32-S3-DevKitC-1 (dual USB-C UART/USB; typically WROOM-1 module)
#define BOARD_TTGO_T_DISPLAY 0
#define BOARD_ESP32_S3_DEVKITC_1 1
#define ACTIVE_BOARD BOARD_ESP32_S3_DEVKITC_1  // BOARD_TTGO_T_DISPLAY or BOARD_ESP32_S3_DEVKITC_1

#if ACTIVE_BOARD != BOARD_TTGO_T_DISPLAY && ACTIVE_BOARD != BOARD_ESP32_S3_DEVKITC_1
#error "Set ACTIVE_BOARD to BOARD_ESP32_S3_DEVKITC_1 or BOARD_TTGO_T_DISPLAY"
#endif

// =============================================================================
// SIGNAL OUTPUT PATH
// =============================================================================
// 0 = Pin_A..F PWM+RC -> amplifiers -> exciters
// 1 = Pin_A=L Pin_B=R I2S -> PCM5102 -> HW-104 -> shakers (C–F unused)
#define OUTPUT_PATH_PWM_RC 0
#define OUTPUT_PATH_PCM5102 1
#define ACTIVE_OUTPUT_PATH OUTPUT_PATH_PCM5102

#if ACTIVE_OUTPUT_PATH != OUTPUT_PATH_PWM_RC && ACTIVE_OUTPUT_PATH != OUTPUT_PATH_PCM5102
#error "Set ACTIVE_OUTPUT_PATH to OUTPUT_PATH_PWM_RC or OUTPUT_PATH_PCM5102"
#endif

// =============================================================================
// I2S DAC SHAKE FEEL (PCM5102 path)
// =============================================================================
// OSC 0..1 maps to shake carrier frequency: 0 -> MIN Hz, 1 -> MAX Hz (per L/R channel).
#define I2S_CARRIER_HZ_MIN 50.0f
#define I2S_CARRIER_HZ_MAX 1500.0f
// How fast L/R levels ease toward new OSC values (0..1). Higher = snappier; lower = smoother.
#define I2S_AMP_SMOOTHING 0.90f
// Exact 0 = silent. Any OSC > 0 remaps into [FLOOR, 1] so weak quakes still shake.
#define SHAKE_LEVEL_FLOOR 0.2f


// =============================================================================
// PWM RC OUTPUT PINS (Pin_A .. Pin_F)
// =============================================================================
// RDCC slots — also one PWM GPIO per slot on the PWM+RC path.
#define MAX_PINS 6
// Used when ACTIVE_OUTPUT_PATH == OUTPUT_PATH_PWM_RC.
#if ACTIVE_BOARD == BOARD_ESP32_S3_DEVKITC_1

// Left-header cluster on DevKitC-1: adjacent, PWM-capable, avoids BOOT/USB/UART/strap/flash.
// Avoid: 0 (BOOT), 19/20 (USB), 43/44 (UART0), 45/46 (strap),
// 35–37 (octal flash on many WROOM-1 modules), 38/48 (onboard LEDs).
static const int PWM_TACTILE_PINS[MAX_PINS] = {4, 5, 6, 7, 15, 16};
#else  // BOARD_TTGO_T_DISPLAY
static const int PWM_TACTILE_PINS[MAX_PINS] = {25, 26, 27, 32, 33, 13};
#endif

// =============================================================================
// OSC ADDRESSING
// =============================================================================
#define OSC_PATH "/red_dust/osc_object_1"
#define OSC_PORT 8000
// No Serial/OSC packet for this long -> treat stream as idle and mute (avoids pops on brief drops).
#define STREAM_IDLE_TIMEOUT_MS 3000
// Clear a partial Serial line if no new characters arrive for this long.
#define SERIAL_TIMEOUT_MS 1000

// =============================================================================
// PWM TACTILE FEEL (PWM+RC path)
// =============================================================================
// OSC/Serial 0..1 is the wave envelope (quake intensity over time). It amplitude-
// modulates a sine; we do NOT time-smear that envelope (so onsets stay sharp).
//
// Shake carrier (Hz): haptic tone under the envelope. Lower = heavier feel.
#define PWM_TACTILE_CARRIER_HZ 32.0f

// How hard OSC=1.0 hits the shaker (0..1). THIS is the fidelity-vs-pop balance:
// raise for stronger shake, lower if peaks still slap the coil. Try 0.75–0.95.
#define PWM_TACTILE_DRIVE 0.88f

// Tiny envelope smooth (ms): only kills packet/quantization clicks, not quake onsets.
#define PWM_TACTILE_SMOOTH_MS 5

// =============================================================================
// SUPPORT / HARDWARE — leave alone unless changing circuit, protocol, or board extras
// =============================================================================

// =============================================================================
// OUTPUT PATH ENABLES (derived from ACTIVE_OUTPUT_PATH)
// =============================================================================
#if ACTIVE_OUTPUT_PATH == OUTPUT_PATH_PCM5102
#define ENABLE_I2S_PCM5102 1
#define ENABLE_TACTILE_OUTPUT 0
#else  // OUTPUT_PATH_PWM_RC
#define ENABLE_I2S_PCM5102 0
#define ENABLE_TACTILE_OUTPUT 1
#endif

// =============================================================================
// I2S OUTPUT PINS (PCM5102)
// =============================================================================
// Used when ACTIVE_OUTPUT_PATH == OUTPUT_PATH_PCM5102.
// Macros stay defined so i2s_audio.cpp compiles; driver starts only if ENABLE_I2S_PCM5102.
#if ACTIVE_BOARD == BOARD_ESP32_S3_DEVKITC_1
#define I2S_BCK_PIN 2
#define I2S_WS_PIN 17
#define I2S_DOUT_PIN 18
#else  // BOARD_TTGO_T_DISPLAY
#define I2S_BCK_PIN 2
#define I2S_WS_PIN 17
#define I2S_DOUT_PIN 22
#endif

// =============================================================================
// STATUS LED (DevKitC-1 only — always on when that board is selected)
// =============================================================================
// Onboard WS2812: red = idle, blue = Pin_A while serial/OSC active
// DevKitC-1 v1.1 silkscreen: GPIO38 (v1.0 used GPIO48)
#if ACTIVE_BOARD == BOARD_ESP32_S3_DEVKITC_1
#define STATUS_RGB_LED_PIN 38
#endif

// =============================================================================
// PWM CHANNEL ROUTING & PER-CHANNEL CAPS
// =============================================================================
#define TACTILE_ROUTE_PWM 1

struct TactileRoute {
  uint8_t type;
  uint8_t index;
};

static const TactileRoute TACTILE_ROUTES[MAX_PINS] = {
    {TACTILE_ROUTE_PWM, 0},  // Pin_A -> PWM_TACTILE_PINS[0] + RC
    {TACTILE_ROUTE_PWM, 1},  // Pin_B -> PWM_TACTILE_PINS[1] + RC
    {TACTILE_ROUTE_PWM, 2},  // Pin_C -> PWM_TACTILE_PINS[2] + RC
    {TACTILE_ROUTE_PWM, 3},  // Pin_D -> PWM_TACTILE_PINS[3] + RC
    {TACTILE_ROUTE_PWM, 4},  // Pin_E -> PWM_TACTILE_PINS[4] + RC
    {TACTILE_ROUTE_PWM, 5},  // Pin_F -> PWM_TACTILE_PINS[5] + RC
};

// Per-channel max drive (0..1). Scale a channel down for weaker exciters
// (e.g. 5W DAEX19 ≈ 0.3) without changing the global feel.
static const float TACTILE_MAX_LEVEL[MAX_PINS] = {1.0f, 1.0f, 1.0f, 1.0f, 0.3f, 0.3f};

// =============================================================================
// I2S DRIVER / DAC PLUMBING
// =============================================================================
// PCM audio rate sent to the DAC (Hz). Leave at 44100 unless changing the I2S driver.
#define I2S_SAMPLE_RATE 44100
// Extra amplitude multiplier after OSC level (1.0 = unity; >1 louder, may clip near peaks).
#define I2S_VOLUME_GAIN 1.0f
// I2S DMA buffer count and samples-per-buffer (latency vs CPU). Leave unless underruns.
#define I2S_DMA_BUF_COUNT 8
#define I2S_DMA_BUF_LEN 256
#define I2S_LEFT_PIN_INDEX 0   // Pin_A -> left
#define I2S_RIGHT_PIN_INDEX 1  // Pin_B -> right

// =============================================================================
// PWM HARDWARE
// =============================================================================
// Leave alone unless changing the circuit.
#define PWM_MIN 0
#define PWM_MAX 255
#define PWM_FREQUENCY 50000
#define PWM_RESOLUTION 8
#define PWM_TACTILE_UPDATE_HZ 5000
// RC: ~1 kΩ + 100–220 nF (pass ~30 Hz, kill 50 kHz). Not 10 µF.

// =============================================================================
// SERIAL
// =============================================================================
#define SERIAL_BAUDRATE 115200
#define SERIAL_STATUS_DEBUG 1  // keep off: Serial is the live data link (TX spam can disturb RX)
#define DISPLAY_BOOT_TEST 1

// Debug Serial helpers: real prints when SERIAL_STATUS_DEBUG, else compile to no-ops.
#if SERIAL_STATUS_DEBUG
#define serialDebugPrintln(...) Serial.println(__VA_ARGS__)
#define serialDebugPrintf(...) Serial.printf(__VA_ARGS__)
#else
#define serialDebugPrintln(...) ((void)0)
#define serialDebugPrintf(...) ((void)0)
#endif

// =============================================================================
// DISPLAY GRAPH COLORS
// =============================================================================
#define GRAPH_GRID_COLOR 0x001F
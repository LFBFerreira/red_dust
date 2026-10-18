#pragma once

// Configuration settings for Lilygo Vibration Controller.
// Board, signal path, and output GPIOs live in board_select.h (included below).

#include "board_select.h"

// =============================================================================
// I2S DAC SHAKE FEEL (PCM5102 path)
// =============================================================================
// OSC 0..1 maps to shake carrier frequency: 0 -> MIN Hz, 1 -> MAX Hz (per L/R channel).
#define I2S_CARRIER_HZ_MIN 25.0f
#define I2S_CARRIER_HZ_MAX 50.0f
// How fast L/R levels ease toward new OSC values (0..1). Higher = snappier; lower = smoother.
#define I2S_AMP_SMOOTHING 0.92f
// Exact 0 = silent. Any OSC > 0 remaps into [FLOOR, 1] so weak quakes still shake.
#define SHAKE_LEVEL_FLOOR 0.2f

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
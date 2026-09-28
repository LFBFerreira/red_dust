// Configuration settings for Lilygo Vibration Controller
// Output path chooses PWM+RC (up to 6 channels) or PCM5102 stereo shake (Pin_A/B only).

// --- Board select (PWM / I2S pin maps) ---
// 0 = LilyGo TTGO T-Display (classic ESP32)
// 1 = ESP32-S3-DevKitC-1 (dual USB-C UART/USB; typically WROOM-1 module)
#define BOARD_TTGO_T_DISPLAY 0
#define BOARD_ESP32_S3_DEVKITC_1 1
#define ACTIVE_BOARD BOARD_ESP32_S3_DEVKITC_1

// --- Output path (compile-time) ---
// 0 = Pin_A..F PWM+RC -> amplifiers -> exciters
// 1 = Pin_A=L Pin_B=R I2S -> PCM5102 -> HW-104 -> shakers (C–F unused)
#define OUTPUT_PATH_PWM_RC 0
#define OUTPUT_PATH_PCM5102 1
#define ACTIVE_OUTPUT_PATH OUTPUT_PATH_PCM5102

#if ACTIVE_OUTPUT_PATH == OUTPUT_PATH_PCM5102
#define ENABLE_I2S_PCM5102 1
#define ENABLE_TACTILE_OUTPUT 0
#elif ACTIVE_OUTPUT_PATH == OUTPUT_PATH_PWM_RC
#define ENABLE_I2S_PCM5102 0
#define ENABLE_TACTILE_OUTPUT 1
#else
#error "Set ACTIVE_OUTPUT_PATH to OUTPUT_PATH_PWM_RC or OUTPUT_PATH_PCM5102"
#endif

// Onboard WS2812 status LED (DevKitC-1 only): red = idle, blue = Pin_A while serial/OSC active
#if ACTIVE_BOARD == BOARD_ESP32_S3_DEVKITC_1
#define ENABLE_STATUS_RGB_LED 1
// DevKitC-1 v1.1 silkscreen: GPIO38 (v1.0 used GPIO48)
#define STATUS_RGB_LED_PIN 38
#else
#define ENABLE_STATUS_RGB_LED 0
#endif

// RDCC slots (Pin_A .. Pin_F)
#define MAX_PINS 6

// --- PWM+RC outputs: one GPIO per channel (Pin_A .. Pin_F) ---
// Used when ACTIVE_OUTPUT_PATH == OUTPUT_PATH_PWM_RC.
#define PWM_TACTILE_COUNT 6

#if ACTIVE_BOARD == BOARD_ESP32_S3_DEVKITC_1
// Left-header cluster on DevKitC-1: adjacent, PWM-capable, avoids BOOT/USB/UART/strap/flash.
// Avoid: 0 (BOOT), 19/20 (USB), 43/44 (UART0), 45/46 (strap),
// 35–37 (octal flash on many WROOM-1 modules), 38/48 (onboard LEDs).
static const int PWM_TACTILE_PINS[PWM_TACTILE_COUNT] = {4, 5, 6, 7, 15, 16};

#elif ACTIVE_BOARD == BOARD_TTGO_T_DISPLAY
static const int PWM_TACTILE_PINS[PWM_TACTILE_COUNT] = {25, 26, 27, 32, 33, 13};
#else
#error "Set ACTIVE_BOARD to BOARD_ESP32_S3_DEVKITC_1 or BOARD_TTGO_T_DISPLAY"
#endif

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

// --- PCM5102 I2S (used when ACTIVE_OUTPUT_PATH == OUTPUT_PATH_PCM5102) ---
// Macros stay defined so i2s_audio.cpp compiles; driver starts only if ENABLE_I2S_PCM5102.
#if ACTIVE_BOARD == BOARD_ESP32_S3_DEVKITC_1
#define I2S_BCK_PIN 2
#define I2S_WS_PIN 17
#define I2S_DOUT_PIN 18
#elif ACTIVE_BOARD == BOARD_TTGO_T_DISPLAY
#define I2S_BCK_PIN 2
#define I2S_WS_PIN 17
#define I2S_DOUT_PIN 22
#else
#error "Set ACTIVE_BOARD to BOARD_ESP32_S3_DEVKITC_1 or BOARD_TTGO_T_DISPLAY"
#endif

#define I2S_SAMPLE_RATE 44100
// Shake carrier (Hz): OSC 0..1 is volume envelope over this tone (quake intensity).
#define I2S_CARRIER_HZ 32.0f
#define I2S_VOLUME_GAIN 1.0f
#define I2S_AMP_SMOOTHING 0.04f
#define I2S_DMA_BUF_COUNT 8
#define I2S_DMA_BUF_LEN 256
#define I2S_LEFT_PIN_INDEX 0   // Pin_A -> left
#define I2S_RIGHT_PIN_INDEX 1  // Pin_B -> right

// Serial / OSC
#define SERIAL_BAUDRATE 115200
#define SERIAL_STATUS_DEBUG 0  // keep off: Serial is the live data link (TX spam can disturb RX)
#define DISPLAY_BOOT_TEST 1

// Debug Serial helpers: real prints when SERIAL_STATUS_DEBUG, else compile to no-ops.
#if SERIAL_STATUS_DEBUG
#define serialDebugPrint(...) Serial.print(__VA_ARGS__)
#define serialDebugPrintln(...) Serial.println(__VA_ARGS__)
#define serialDebugPrintf(...) Serial.printf(__VA_ARGS__)
#else
#define serialDebugPrint(...) ((void)0)
#define serialDebugPrintln(...) ((void)0)
#define serialDebugPrintf(...) ((void)0)
#endif

#define OSC_PATH "/red_dust/osc_object_1"
#define OSC_PORT 8000

// --- Tactile feel (PWM path; tune these) ---
// OSC/Serial 0..1 is the wave envelope (quake intensity over time). It amplitude-
// modulates a sine; we do NOT time-smear that envelope (so onsets stay sharp).
//
// Shake carrier (Hz): haptic tone under the envelope. Lower = heavier feel.
#define PWM_TACTILE_CARRIER_HZ 32.0f
// How hard OSC=1.0 hits the shaker (0..1). THIS is the fidelity-vs-pop balance:
// raise for stronger shake, lower if peaks still slap the coil. Try 0.75–0.95.
#define PWM_TACTILE_DRIVE 0.88f

// --- PWM hardware (leave alone unless changing the circuit) ---
#define PWM_MIN 0
#define PWM_MAX 255
#define PWM_FREQUENCY 50000
#define PWM_RESOLUTION 8
#define PWM_TACTILE_UPDATE_HZ 5000
// Tiny envelope smooth (ms): only kills packet/quantization clicks, not quake onsets.
#define PWM_TACTILE_SMOOTH_MS 5
// RC: ~1 kΩ + 100–220 nF (pass ~30 Hz, kill 50 kHz). Not 10 µF.

#define GRAPH_GRID_COLOR 0x001F
#define GRAPH_TRACE_COLOR 0xF800

// Backward-compatible aliases (older docs / snippets)
#define ENABLE_I2S_AUDIO ENABLE_I2S_PCM5102
#define ENABLE_PWM_OUTPUT ENABLE_TACTILE_OUTPUT

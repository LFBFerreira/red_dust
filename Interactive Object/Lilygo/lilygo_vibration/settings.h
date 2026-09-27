// Configuration settings for Lilygo Vibration Controller
// 6 transducers (Pin_A .. Pin_F), all driven via PWM+RC -> amplifiers -> exciters

// --- Board select (PWM pin map) ---
// 0 = LilyGo TTGO T-Display (classic ESP32)
// 1 = ESP32-S3-DevKitC-1 (dual USB-C UART/USB; typically WROOM-1 module)
#define BOARD_TTGO_T_DISPLAY 0
#define BOARD_ESP32_S3_DEVKITC_1 1
#define ACTIVE_BOARD BOARD_ESP32_S3_DEVKITC_1

// --- Feature switches ---
#define ENABLE_TACTILE_OUTPUT 1   // PWM+RC -> amplifier inputs
#define ENABLE_I2S_PCM5102 0      // No audio/bone-conduction path; all channels are PWM tactile
#define ENABLE_MCP4725 0          // No DAC channels anymore; everything is PWM+RC

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

// --- MCP4725 DAC (disabled; kept for backward compatibility) ---
#if ENABLE_MCP4725
#define MCP4725_COUNT 1
static const uint8_t MCP4725_I2C_ADDR[MCP4725_COUNT] = {0x60};
#define I2C_SDA_PIN 21
#define I2C_SCL_PIN 15
#else
#define MCP4725_COUNT 0
#endif


// --- PWM+RC outputs: one GPIO per channel (Pin_A .. Pin_F) ---
// All pins must be PWM-capable, output-capable, and free on the selected board.
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

// Per Pin_A..F: driver for amplifier path
// type 0 = MCP4725 (index into DAC array), type 1 = PWM+RC (index into PWM_TACTILE_PINS)
#define TACTILE_ROUTE_MCP4725 0
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

// Per-channel output ceiling (0..1) applied before PWM mapping. Use this to protect
// lower-power exciters: e.g. DAEX19CT-4 (5W) vs DAEX25VT-4 (20W). Set the 5W channels
// to a lower value so they never reach full drive. 1.0 = no limit.
// Pin_A/B/C/D -> DAEX25VT-4 (20W): full range. Pin_E/F -> DAEX19CT-4 (5W): capped at 0.3.
static const float TACTILE_MAX_LEVEL[MAX_PINS] = {1.0f, 1.0f, 1.0f, 1.0f, 0.3f, 0.3f};

// --- Optional PCM5102 (feature disabled above; macros kept defined so i2s_audio.cpp
//     still compiles. With ENABLE_I2S_PCM5102 0 the I2S driver is never started and
//     these pins stay free.) ---
#define I2S_BCK_PIN 2
#define I2S_WS_PIN 17
#define I2S_DOUT_PIN 22
#define I2S_SAMPLE_RATE 44100
#define I2S_CARRIER_HZ 400.0f
#define I2S_VOLUME_GAIN 1.0f
#define I2S_AMP_SMOOTHING 0.04f
#define I2S_DMA_BUF_COUNT 8
#define I2S_DMA_BUF_LEN 256
#define I2S_LEFT_PIN_INDEX 0
#define I2S_RIGHT_PIN_INDEX 1
#define I2S_DEFAULT_OUTPUT_MODE 0

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

// PWM (tactile filtered outputs)
#define PWM_MIN 0
#define PWM_MAX 255
#define PWM_FREQUENCY 25000
#define PWM_RESOLUTION 8

#define GRAPH_GRID_COLOR 0x001F
#define GRAPH_TRACE_COLOR 0xF800

// Backward-compatible aliases (older docs / snippets)
#define ENABLE_I2S_AUDIO ENABLE_I2S_PCM5102
#define ENABLE_PWM_OUTPUT ENABLE_TACTILE_OUTPUT

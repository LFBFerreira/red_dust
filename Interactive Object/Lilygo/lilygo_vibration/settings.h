// Configuration settings for Lilygo Vibration Controller
// 4 transducers: Pin_A/B -> MCP4725, Pin_C/D -> PWM+RC, optional PCM5102 (I2S) for audio

// --- Feature switches ---
#define ENABLE_TACTILE_OUTPUT 1   // MCP4725 + PWM+RC -> HW-104 inputs
#define ENABLE_I2S_PCM5102 1      // Optional I2S -> PCM5102 (AUDIO mode); not used for tactile

// RDCC slots (Pin_A .. Pin_D)
#define MAX_PINS 4

// --- Tactile: two MCP4725 (one channel each) + two PWM+RC ---
#define MCP4725_COUNT 2
// Strap A0 on second module to VDD for 0x61 (first board default 0x60)
static const uint8_t MCP4725_I2C_ADDR[MCP4725_COUNT] = {0x60, 0x61};

#define I2C_SDA_PIN 21
#define I2C_SCL_PIN 15

#define PWM_TACTILE_COUNT 2
static const int PWM_TACTILE_PINS[PWM_TACTILE_COUNT] = {27, 32};

// Per Pin_A..D: driver for HW-104 path
// type 0 = MCP4725 (index 0 or 1), type 1 = PWM+RC (index 0 or 1)
#define TACTILE_ROUTE_MCP4725 0
#define TACTILE_ROUTE_PWM 1

struct TactileRoute {
  uint8_t type;
  uint8_t index;
};

static const TactileRoute TACTILE_ROUTES[MAX_PINS] = {
    {TACTILE_ROUTE_MCP4725, 0},  // Pin_A -> MCP4725 #0 (0x60)
    {TACTILE_ROUTE_MCP4725, 1},  // Pin_B -> MCP4725 #1 (0x61)
    {TACTILE_ROUTE_PWM, 0},      // Pin_C -> PWM GPIO 27 + RC
    {TACTILE_ROUTE_PWM, 1},      // Pin_D -> PWM GPIO 32 + RC
};

// --- Optional PCM5102 (separate from tactile transducers) ---
#define I2S_BCK_PIN 2
#define I2S_WS_PIN 17
#define I2S_DOUT_PIN 22
#define I2S_SAMPLE_RATE 44100
#define I2S_CARRIER_HZ 400.0f
#define I2S_VOLUME_GAIN 1.0f
#define I2S_AMP_SMOOTHING 0.04f
#define I2S_DMA_BUF_COUNT 8
#define I2S_DMA_BUF_LEN 256
// PCM5102 sonification listens to these RDCC indices (usually same as Pin_A/B)
#define I2S_LEFT_PIN_INDEX 0
#define I2S_RIGHT_PIN_INDEX 1
#define I2S_DEFAULT_OUTPUT_MODE 0  // 0=mute PCM5102 at boot, 1=AUDIO; tactile always MCP4725/PWM

// Serial / OSC
#define SERIAL_BAUDRATE 115200
#define SERIAL_STATUS_DEBUG 1
#define DISPLAY_BOOT_TEST 1

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

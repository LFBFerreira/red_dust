// Dust Devil — story-clock companion to lilygo_vibration
// 6 transducers (Pin_A .. Pin_F), PWM+RC -> amplifiers -> exciters
// Pin on/off timing is authored in RDCC; this firmware just plays the stream.

#define ENABLE_TACTILE_OUTPUT 1
#define ENABLE_MCP4725 0
#define ENABLE_DY_HV20T 1

// DY uses GPIO 17/21/22. Do not enable I2S or MCP4725 on this sketch.

#define MAX_PINS 6

#if ENABLE_MCP4725
#define MCP4725_COUNT 1
static const uint8_t MCP4725_I2C_ADDR[MCP4725_COUNT] = {0x60};
#define I2C_SDA_PIN 21
#define I2C_SCL_PIN 15
#else
#define MCP4725_COUNT 0
#endif

#define PWM_TACTILE_COUNT 6
static const int PWM_TACTILE_PINS[PWM_TACTILE_COUNT] = {25, 26, 27, 32, 33, 13};

#define TACTILE_ROUTE_MCP4725 0
#define TACTILE_ROUTE_PWM 1

struct TactileRoute {
  uint8_t type;
  uint8_t index;
};

static const TactileRoute TACTILE_ROUTES[MAX_PINS] = {
    {TACTILE_ROUTE_PWM, 0},  // Pin_A -> PWM GPIO 25 + RC
    {TACTILE_ROUTE_PWM, 1},  // Pin_B -> PWM GPIO 26 + RC
    {TACTILE_ROUTE_PWM, 2},  // Pin_C -> PWM GPIO 27 + RC
    {TACTILE_ROUTE_PWM, 3},  // Pin_D -> PWM GPIO 32 + RC
    {TACTILE_ROUTE_PWM, 4},  // Pin_E -> PWM GPIO 33 + RC
    {TACTILE_ROUTE_PWM, 5},  // Pin_F -> PWM GPIO 13 + RC
};

// Pin_A/B/C/D -> DAEX25VT-4 (20W). Pin_E/F -> DAEX19CT-4 (5W): capped at 0.3.
static const float TACTILE_MAX_LEVEL[MAX_PINS] = {1.0f, 1.0f, 1.0f, 1.0f, 0.3f, 0.3f};

#if ENABLE_DY_HV20T
#define DY_UART_NUM 1
#define DY_TX_PIN 17
#define DY_RX_PIN -1
#define DY_BAUD 9600
#define DY_PIN_PLAY_BTN 21
#define DY_PIN_STOP_BTN 22
#define DY_BTN_DEBOUNCE_MS 40
#define DY_SEND_STOP_ON_BOOT 1
#define DY_GATE_TACTILE_OUTPUT 1
// UART digital volume (0–30). Default on the module is 20. The onboard pot
// usually drives the speaker amp, not the headphone/DAC jack.
#define DY_VOLUME 30
#endif

#define SERIAL_BAUDRATE 115200
#define SERIAL_STATUS_DEBUG 1
#define DISPLAY_BOOT_TEST 1

#define OSC_PATH "/red_dust/dust_devil"
#define OSC_PORT 8000

#define PWM_MIN 0
#define PWM_MAX 255
#define PWM_FREQUENCY 25000
#define PWM_RESOLUTION 8

#define GRAPH_GRID_COLOR 0x001F
#define GRAPH_TRACE_COLOR 0xF800

#define ENABLE_PWM_OUTPUT ENABLE_TACTILE_OUTPUT

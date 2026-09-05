// Croissant — one LilyGO T-Display per station.
// Both boards use the same GPIOs. Set STATION_ID to 1 or 2 before upload.
// Pin on/off timing is authored in Croissant Control Center.

#define ENABLE_TACTILE_OUTPUT 1
#define ENABLE_MCP4725 0
#define ENABLE_DY_HV20T 1

// 1 = Station 1 (Pin_A/B clock, DY1). 2 = Station 2 (Pin_A/B clock, DY2).
#define STATION_ID 2

#define PINS_PER_STATION 2
#define MAX_PINS PINS_PER_STATION
#define WIRE_MAX_INCOMING 4

#if STATION_ID == 1
#define OSC_PATH "/red_dust/croissant/1"
#define WIFI_AP_NAME "Red_Dust_Croissant1"
#else
#define OSC_PATH "/red_dust/croissant/2"
#define WIFI_AP_NAME "Red_Dust_Croissant2"
#endif

#if ENABLE_MCP4725
#define MCP4725_COUNT 1
static const uint8_t MCP4725_I2C_ADDR[MCP4725_COUNT] = {0x60};
#define I2C_SDA_PIN 21
#define I2C_SCL_PIN 15
#else
#define MCP4725_COUNT 0
#endif

#define PWM_TACTILE_COUNT 2
static const int PWM_TACTILE_PINS[PWM_TACTILE_COUNT] = {25, 26};

#define TACTILE_ROUTE_MCP4725 0
#define TACTILE_ROUTE_PWM 1

struct TactileRoute {
  uint8_t type;
  uint8_t index;
};

static const TactileRoute TACTILE_ROUTES[MAX_PINS] = {
    {TACTILE_ROUTE_PWM, 0},  // Pin_A -> PWM GPIO 25 + RC
    {TACTILE_ROUTE_PWM, 1},  // Pin_B -> PWM GPIO 26 + RC
};

static const float TACTILE_MAX_LEVEL[MAX_PINS] = {1.0f, 1.0f};

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
#define DY_VOLUME 30
#endif

#define SERIAL_BAUDRATE 115200
#define SERIAL_STATUS_DEBUG 1
#define DISPLAY_BOOT_TEST 1

#define OSC_PORT 8000

#define PWM_MIN 0
#define PWM_MAX 255
#define PWM_FREQUENCY 25000
#define PWM_RESOLUTION 8

#define GRAPH_GRID_COLOR 0x001F
#define GRAPH_TRACE_COLOR 0xF800

#define ENABLE_PWM_OUTPUT ENABLE_TACTILE_OUTPUT

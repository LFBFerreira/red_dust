// Configuration settings for Lilygo Vibration Controller
// This file contains all user-configurable constants

// Multi-pin output (must match RDCC Pin_A.. order; max 5 slots)
#define MAX_PINS 5
// GPIO order: Pin_A, Pin_B, Pin_C, Pin_D, Pin_E (PWM-capable pins on typical TTGO T-Display)
static const int OUTPUT_PINS[MAX_PINS] = {25, 26, 27, 32, 33};

// Serial communication configuration
#define SERIAL_BAUDRATE 115200  // Serial communication baud rate

// OSC / Serial multi-pin: N floats (Pin_A..) + timestamp. Values in [0,1] drive PWM;
// values outside [0,1] mean that slot is inactive (padding / no channel), PWM off.
const char* OSC_PATH = "/red_dust/osc_object_1";
#define OSC_PORT 8000  // UDP port for OSC messages

// PWM mapping configuration
#define PWM_MIN 0      // Minimum PWM value (motor off)
#define PWM_MAX 255    // Maximum PWM value (full intensity)

// ESP32 LEDC PWM configuration (for ESP32 Arduino core 3.x)
#define PWM_FREQUENCY 5000    // PWM frequency in Hz (5kHz is good for motors)
#define PWM_RESOLUTION 8      // 8-bit resolution (0-255)

// Graph display colors (RGB565 format)
// Note: These will be used after TFT_eSPI is included, so TFT color constants are available
#define GRAPH_GRID_COLOR TFT_BLUE   // Color for graph grid lines
#define GRAPH_TRACE_COLOR TFT_RED   // Legacy single-trace color (Pin_A uses first overlay color in .ino)

// Configuration settings for Lilygo Vibration Controller
// This file contains all user-configurable constants

// Serial communication configuration
#define SERIAL_BAUDRATE 115200  // Serial communication baud rate

// OSC configuration
const char* OSC_PATH = "/red_dust/osc_object_1";  // OSC path to listen for
#define OSC_PORT 8000  // UDP port for OSC messages

// Configuration constants
#define VIBRATION_MOTOR_PIN 25  // PWM pin for vibration motor (GPIO 25 - safe for ESP32)
// Note: Avoid pins 0, 2, 4, 12-15, 25-27 if using display
// GPIO 25 is typically safe for PWM on TTGO T-Display

// PWM mapping configuration
#define PWM_MIN 0      // Minimum PWM value (motor off)
#define PWM_MAX 255    // Maximum PWM value (full intensity)

// ESP32 LEDC PWM configuration (for ESP32 Arduino core 3.x)
#define PWM_FREQUENCY 5000    // PWM frequency in Hz (5kHz is good for motors)
#define PWM_RESOLUTION 8      // 8-bit resolution (0-255)

// Graph display colors (RGB565 format)
// Note: These will be used after TFT_eSPI is included, so TFT color constants are available
#define GRAPH_GRID_COLOR TFT_BLUE   // Color for graph grid lines
#define GRAPH_TRACE_COLOR TFT_RED   // Color for graph trace line
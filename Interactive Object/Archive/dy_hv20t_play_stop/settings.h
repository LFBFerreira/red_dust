// DY-HV20T Play / Stop controller for LilyGO TTGO T-Display
// Pins below avoid the tactile PWM set used by lilygo_vibration
// (25, 26, 27, 32, 33, 13).

// --- Buttons (momentary, to GND; INPUT_PULLUP) ---
// Default: free GPIOs for two external push buttons.
// Alternative: T-Display onboard buttons — set PLAY=0, STOP=35
// (GPIO 35 is input-only and has no internal pull-up; onboard OK).
#define PIN_PLAY_BTN 21
#define PIN_STOP_BTN 22

// --- UART to DY-HV20T (9600 8N1, UART Mode: CON3=1 CON2=0 CON1=0) ---
// ESP32 TX -> DY IO1/RXD. RX optional (status queries).
#define DY_UART_NUM 1
#define DY_TX_PIN 17   // ESP TX  -> DY RXD (IO1)
#define DY_RX_PIN -1   // set to a free GPIO (e.g. 2) if you need replies
#define DY_BAUD 9600

// Debounce for momentary buttons (ms)
#define BTN_DEBOUNCE_MS 40

// Optional onboard TFT status (needs TFT_eSPI Setup25_TTGO_T_Display)
#define ENABLE_DISPLAY 1
#define TFT_BL_PIN 4

// Boot: send Stop once so module starts quiet
#define SEND_STOP_ON_BOOT 1

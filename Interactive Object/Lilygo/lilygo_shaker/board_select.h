#pragma once

// Pick the board, the signal path, and the output GPIOs here, then recompile.
// Shake feel, OSC, and serial stay in settings.h.

// =============================================================================
// BOARD SELECT
// =============================================================================
// 0 = LilyGo TTGO T-Display (classic ESP32)
// 1 = ESP32-S3-DevKitC-1 (dual USB-C UART/USB; typically WROOM-1 module)
#define BOARD_TTGO_T_DISPLAY 0
#define BOARD_ESP32_S3_DEVKITC_1 1
#define ACTIVE_BOARD BOARD_TTGO_T_DISPLAY  // BOARD_TTGO_T_DISPLAY or BOARD_ESP32_S3_DEVKITC_1

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
#define ACTIVE_OUTPUT_PATH OUTPUT_PATH_PCM5102  // OUTPUT_PATH_PWM_RC or OUTPUT_PATH_PCM5102

#if ACTIVE_OUTPUT_PATH != OUTPUT_PATH_PWM_RC && ACTIVE_OUTPUT_PATH != OUTPUT_PATH_PCM5102
#error "Set ACTIVE_OUTPUT_PATH to OUTPUT_PATH_PWM_RC or OUTPUT_PATH_PCM5102"
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
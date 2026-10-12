#pragma once

#include <Arduino.h>
#include "settings.h"

// Board-specific UI: TFT graph (TTGO) and/or status RGB LED (DevKitC-1).

void ui_begin();
void ui_update(const float* pinValues, bool streamActive);

// Graph: call after each accepted pin frame (no-op on boards without TFT).
void ui_onPinFrame(const float* pinValues, const bool* slotLive, int incomingCount);

#if ACTIVE_BOARD == BOARD_ESP32_S3_DEVKITC_1
void ui_statusLedBootTest();
void ui_statusLedShowIdle();
void ui_statusLedInvalidate();
void ui_statusLedUpdate(bool streamActive, float pinALevel);
#endif

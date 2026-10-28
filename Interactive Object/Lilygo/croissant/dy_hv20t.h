#pragma once

#include <Arduino.h>

// DY-HV20T UART play/stop. Enable via ENABLE_DY_HV20T in settings.h.

bool dy_hv20t_begin();
void dy_hv20t_update();  // poll buttons (call from loop)
void dy_hv20t_play();
void dy_hv20t_stop();
void dy_hv20t_set_volume(uint8_t volume);  // 0–30
bool dy_hv20t_is_playing();

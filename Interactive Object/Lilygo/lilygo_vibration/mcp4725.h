#pragma once

#include <Arduino.h>

bool mcp4725_begin();
void mcp4725_write(uint8_t deviceIndex, uint16_t value12);  // 0..4095
void mcp4725_write_level(uint8_t deviceIndex, float level01);  // 0..1

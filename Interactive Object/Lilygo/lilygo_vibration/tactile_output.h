#pragma once

#include <Arduino.h>

bool tactile_output_begin();
void tactile_output_set_level(int pinIndex, float level01);
void tactile_output_apply(bool active);

#pragma once

#include <Arduino.h>

bool i2s_audio_begin();

// OSC Pin_A/B (0..1): L/R volume and carrier Hz (mapped via I2S_CARRIER_HZ_MIN..MAX).
void i2s_audio_set_stereo_levels(float left, float right);

// Sets both channels (legacy / single-channel use)
void i2s_audio_set_target_amplitude(float amplitude);

// Whiteboard: force a fixed carrier (min=max=hz). Pass <=0 to restore settings range.
void i2s_audio_set_carrier_hz(float hz);

void i2s_audio_mute();

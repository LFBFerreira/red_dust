#pragma once

#include <Arduino.h>

bool i2s_audio_begin();

// Shake carrier frequency (Hz). OSC Pin_A/B set L/R volume over this tone.
void i2s_audio_set_carrier_hz(float hz);

// Pin_A -> left, Pin_B -> right (0..1) volume envelopes.
void i2s_audio_set_stereo_levels(float left, float right);

// Sets both channels (legacy / single-channel use)
void i2s_audio_set_target_amplitude(float amplitude);

void i2s_audio_mute();

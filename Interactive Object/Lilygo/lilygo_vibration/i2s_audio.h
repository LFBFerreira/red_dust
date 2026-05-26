#pragma once

#include <Arduino.h>

enum I2sOutputMode : uint8_t {
  I2S_MODE_TACTILE = 0,  // DC level on I2S -> PCM5102 (exciter / haptic)
  I2S_MODE_AUDIO = 1     // Carrier tone; levels = L/R amplitude
};

bool i2s_audio_begin();

void i2s_audio_set_mode(I2sOutputMode mode);
I2sOutputMode i2s_audio_get_mode();

// Carrier for AUDIO mode (Hz)
void i2s_audio_set_carrier_hz(float hz);

// Pin_A -> left, Pin_B -> right (0..1). Used for TACTILE DC and AUDIO envelopes.
void i2s_audio_set_stereo_levels(float left, float right);

// Sets both channels (legacy / single-channel use)
void i2s_audio_set_target_amplitude(float amplitude);

void i2s_audio_mute();

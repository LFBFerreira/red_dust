#include "i2s_audio.h"
#include "settings.h"

#include <driver/i2s.h>
#include <math.h>

static volatile float s_targetL = 0.0f;
static volatile float s_targetR = 0.0f;
static float s_currentL = 0.0f;
static float s_currentR = 0.0f;
static float s_phaseL = 0.0f;
static float s_phaseR = 0.0f;
static volatile float s_hzMin = I2S_CARRIER_HZ_MIN;
static volatile float s_hzMax = I2S_CARRIER_HZ_MAX;
static bool s_ready = false;

#ifndef PI_F
#define PI_F 3.14159265f
#endif

static float sanitizeLevel(float v) {
  if (isnan(v) || isinf(v)) {
    return 0.0f;
  }
  return constrain(v, 0.0f, 1.0f);
}

static float levelToHz(float level01, float hzMin, float hzMax) {
  return hzMin + sanitizeLevel(level01) * (hzMax - hzMin);
}

static void wrapPhase(float* phase) {
  if (*phase >= 2.0f * PI_F) {
    *phase -= 2.0f * PI_F;
  }
}

void i2s_audio_set_carrier_hz(float hz) {
  if (hz <= 0.0f) {
    s_hzMin = I2S_CARRIER_HZ_MIN;
    s_hzMax = I2S_CARRIER_HZ_MAX;
    return;
  }
  if (hz < 15.0f) hz = 15.0f;
  if (hz > 200.0f) hz = 200.0f;
  // Fixed carrier for whiteboard tuning (OSC still scales volume only).
  s_hzMin = hz;
  s_hzMax = hz;
}

void i2s_audio_set_stereo_levels(float left, float right) {
  s_targetL = sanitizeLevel(left);
  s_targetR = sanitizeLevel(right);
}

void i2s_audio_set_target_amplitude(float amplitude) {
  amplitude = sanitizeLevel(amplitude);
  s_targetL = amplitude;
  s_targetR = amplitude;
}

void i2s_audio_mute() {
  s_targetL = 0.0f;
  s_targetR = 0.0f;
}

static void audioStreamTask(void* /*param*/) {
  const size_t frameCount = 256;
  int16_t buffer[frameCount * 2];
  size_t bytesWritten = 0;
  const float smooth = I2S_AMP_SMOOTHING;
  const float sampleRate = (float)I2S_SAMPLE_RATE;

  while (true) {
    s_currentL += (s_targetL - s_currentL) * smooth;
    s_currentR += (s_targetR - s_currentR) * smooth;

    const float hzMin = s_hzMin;
    const float hzMax = s_hzMax;

    for (size_t i = 0; i < frameCount; i++) {
      const float hzL = levelToHz(s_currentL, hzMin, hzMax);
      const float hzR = levelToHz(s_currentR, hzMin, hzMax);

      s_phaseL += (2.0f * PI_F * hzL) / sampleRate;
      s_phaseR += (2.0f * PI_F * hzR) / sampleRate;
      wrapPhase(&s_phaseL);
      wrapPhase(&s_phaseR);

      int32_t left =
          (int32_t)(sinf(s_phaseL) * s_currentL * 32767.0f * I2S_VOLUME_GAIN);
      int32_t right =
          (int32_t)(sinf(s_phaseR) * s_currentR * 32767.0f * I2S_VOLUME_GAIN);
      if (left > 32767) left = 32767;
      if (left < -32768) left = -32768;
      if (right > 32767) right = 32767;
      if (right < -32768) right = -32768;

      buffer[i * 2] = (int16_t)left;
      buffer[i * 2 + 1] = (int16_t)right;
    }

    i2s_write(I2S_NUM_0, buffer, sizeof(buffer), &bytesWritten, portMAX_DELAY);
  }
}

bool i2s_audio_begin() {
  if (s_ready) {
    return true;
  }

  i2s_config_t i2sConfig = {};
  i2sConfig.mode = (i2s_mode_t)(I2S_MODE_MASTER | I2S_MODE_TX);
  i2sConfig.sample_rate = I2S_SAMPLE_RATE;
  i2sConfig.bits_per_sample = I2S_BITS_PER_SAMPLE_16BIT;
  i2sConfig.channel_format = I2S_CHANNEL_FMT_RIGHT_LEFT;
  i2sConfig.communication_format = I2S_COMM_FORMAT_STAND_I2S;
  i2sConfig.intr_alloc_flags = ESP_INTR_FLAG_LEVEL1;
  i2sConfig.dma_buf_count = I2S_DMA_BUF_COUNT;
  i2sConfig.dma_buf_len = I2S_DMA_BUF_LEN;
  i2sConfig.use_apll = false;
  i2sConfig.tx_desc_auto_clear = true;
  i2sConfig.fixed_mclk = 0;

  if (i2s_driver_install(I2S_NUM_0, &i2sConfig, 0, nullptr) != ESP_OK) {
    serialDebugPrintln("I2S: driver_install failed");
    return false;
  }

  i2s_pin_config_t pinConfig = {};
  pinConfig.bck_io_num = I2S_BCK_PIN;
  pinConfig.ws_io_num = I2S_WS_PIN;
  pinConfig.data_out_num = I2S_DOUT_PIN;
  pinConfig.data_in_num = I2S_PIN_NO_CHANGE;

  if (i2s_set_pin(I2S_NUM_0, &pinConfig) != ESP_OK) {
    serialDebugPrintln("I2S: set_pin failed");
    i2s_driver_uninstall(I2S_NUM_0);
    return false;
  }

  i2s_zero_dma_buffer(I2S_NUM_0);
  i2s_set_sample_rates(I2S_NUM_0, I2S_SAMPLE_RATE);

  xTaskCreatePinnedToCore(audioStreamTask, "i2s_pcm", 4096, nullptr, 2, nullptr, 0);

  s_ready = true;
  serialDebugPrintf(
      "I2S -> PCM5102 shake: %u Hz sample, BCK=%d WS=%d DOUT=%d, OSC 0..1 -> %.0f..%.0f Hz + volume\n",
      (unsigned)I2S_SAMPLE_RATE, I2S_BCK_PIN, I2S_WS_PIN, I2S_DOUT_PIN, (double)s_hzMin,
      (double)s_hzMax);
  return true;
}

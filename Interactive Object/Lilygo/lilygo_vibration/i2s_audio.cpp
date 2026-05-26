#include "i2s_audio.h"
#include "settings.h"

#include <driver/i2s.h>
#include <math.h>

static volatile I2sOutputMode s_mode =
    (I2S_DEFAULT_OUTPUT_MODE == 1) ? I2S_MODE_AUDIO : I2S_MODE_TACTILE;

static volatile float s_targetL = 0.0f;
static volatile float s_targetR = 0.0f;
static float s_currentL = 0.0f;
static float s_currentR = 0.0f;
static float s_phase = 0.0f;
static volatile float s_carrierHz = I2S_CARRIER_HZ;
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

static int16_t levelToPcm(float level) {
  int32_t scaled = (int32_t)(sanitizeLevel(level) * 32767.0f * I2S_VOLUME_GAIN);
  if (scaled > 32767) scaled = 32767;
  if (scaled < 0) scaled = 0;
  return (int16_t)scaled;
}

void i2s_audio_set_mode(I2sOutputMode mode) {
  s_mode = mode;
  if (mode == I2S_MODE_TACTILE) {
    s_phase = 0.0f;
  }
}

I2sOutputMode i2s_audio_get_mode() { return s_mode; }

void i2s_audio_set_carrier_hz(float hz) {
  if (hz < 20.0f) hz = 20.0f;
  if (hz > 2000.0f) hz = 2000.0f;
  s_carrierHz = hz;
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

  while (true) {
    s_currentL += (s_targetL - s_currentL) * smooth;
    s_currentR += (s_targetR - s_currentR) * smooth;

    const I2sOutputMode mode = s_mode;
    const float sampleRate = (float)I2S_SAMPLE_RATE;
    const float carrier = s_carrierHz;
    const float phaseStep = (2.0f * PI_F * carrier) / sampleRate;

    if (mode == I2S_MODE_TACTILE) {
      const int16_t pcmL = levelToPcm(s_currentL);
      const int16_t pcmR = levelToPcm(s_currentR);
      for (size_t i = 0; i < frameCount; i++) {
        buffer[i * 2] = pcmL;
        buffer[i * 2 + 1] = pcmR;
      }
    } else {
      for (size_t i = 0; i < frameCount; i++) {
        const float carrierSample = sinf(s_phase);
        s_phase += phaseStep;
        if (s_phase >= 2.0f * PI_F) {
          s_phase -= 2.0f * PI_F;
        }

        int32_t left = (int32_t)(carrierSample * s_currentL * 32767.0f * I2S_VOLUME_GAIN);
        int32_t right = (int32_t)(carrierSample * s_currentR * 32767.0f * I2S_VOLUME_GAIN);
        if (left > 32767) left = 32767;
        if (left < -32768) left = -32768;
        if (right > 32767) right = 32767;
        if (right < -32768) right = -32768;

        buffer[i * 2] = (int16_t)left;
        buffer[i * 2 + 1] = (int16_t)right;
      }
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
    Serial.println("I2S: driver_install failed");
    return false;
  }

  i2s_pin_config_t pinConfig = {};
  pinConfig.bck_io_num = I2S_BCK_PIN;
  pinConfig.ws_io_num = I2S_WS_PIN;
  pinConfig.data_out_num = I2S_DOUT_PIN;
  pinConfig.data_in_num = I2S_PIN_NO_CHANGE;

  if (i2s_set_pin(I2S_NUM_0, &pinConfig) != ESP_OK) {
    Serial.println("I2S: set_pin failed");
    i2s_driver_uninstall(I2S_NUM_0);
    return false;
  }

  i2s_zero_dma_buffer(I2S_NUM_0);
  i2s_set_sample_rates(I2S_NUM_0, I2S_SAMPLE_RATE);

  xTaskCreatePinnedToCore(audioStreamTask, "i2s_pcm", 4096, nullptr, 2, nullptr, 0);

  s_ready = true;
  const char* modeName = (s_mode == I2S_MODE_TACTILE) ? "TACTILE" : "AUDIO";
  Serial.printf("I2S -> PCM5102: %u Hz, BCK=%d WS=%d DOUT=%d, mode=%s",
                (unsigned)I2S_SAMPLE_RATE, I2S_BCK_PIN, I2S_WS_PIN, I2S_DOUT_PIN, modeName);
  if (s_mode == I2S_MODE_AUDIO) {
    Serial.printf(", carrier %.1f Hz", s_carrierHz);
  }
  Serial.println();
  return true;
}

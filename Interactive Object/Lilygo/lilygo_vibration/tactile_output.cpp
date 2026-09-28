#include "tactile_output.h"
#include "settings.h"
#if ENABLE_MCP4725
#include "mcp4725.h"
#endif

#include <esp_timer.h>
#include <math.h>

#ifndef PI_F
#define PI_F 3.14159265f
#endif

static float s_levels[MAX_PINS] = {0};
static float s_smoothed[MAX_PINS] = {0};
static volatile bool s_active = false;
static volatile float s_carrierHz = PWM_TACTILE_CARRIER_HZ;
static float s_phase = 0.0f;
static esp_timer_handle_t s_timer = nullptr;

static int modulatedDuty(float level01, float wave) {
  const float mid = 0.5f * (float)(PWM_MAX + PWM_MIN);
  const float half = 0.5f * (float)(PWM_MAX - PWM_MIN) * PWM_TACTILE_DRIVE;
  float duty = mid + wave * level01 * half;
  int d = (int)(duty + 0.5f);
  return constrain(d, PWM_MIN, PWM_MAX);
}

#if ENABLE_TACTILE_OUTPUT
static void tactileCarrierTick(void* /*arg*/) {
  const float dt = 1.0f / (float)PWM_TACTILE_UPDATE_HZ;
  // One-pole follow of the envelope. SMOOTH_MS≈5 keeps quake onsets sharp.
  const float smoothMs =
      (PWM_TACTILE_SMOOTH_MS < 1) ? 1.0f : (float)PWM_TACTILE_SMOOTH_MS;
  const float smooth = 1.0f - expf(-dt / (smoothMs * 0.001f));

  const bool active = s_active;
  const float carrier = s_carrierHz;
  const float phaseStep = 2.0f * PI_F * carrier * dt;

  float wave = 0.0f;
  if (active) {
    s_phase += phaseStep;
    if (s_phase >= 2.0f * PI_F) {
      s_phase -= 2.0f * PI_F;
    }
    wave = sinf(s_phase);
  } else {
    s_phase = 0.0f;
  }

  for (int pin = 0; pin < MAX_PINS; pin++) {
    const TactileRoute& route = TACTILE_ROUTES[pin];
    float target = active ? s_levels[pin] : 0.0f;
    if (!active) {
      s_smoothed[pin] = 0.0f;
    } else {
      s_smoothed[pin] += (target - s_smoothed[pin]) * smooth;
    }

    if (route.type == TACTILE_ROUTE_MCP4725) {
#if ENABLE_MCP4725
      if (route.index < MCP4725_COUNT) {
        mcp4725_write_level(route.index, s_smoothed[pin]);
      }
#endif
    } else if (route.type == TACTILE_ROUTE_PWM) {
      if (route.index < PWM_TACTILE_COUNT) {
        int gpio = PWM_TACTILE_PINS[route.index];
        int duty = active ? modulatedDuty(s_smoothed[pin], wave) : 0;
        ledcWrite(gpio, duty);
      }
    }
  }
}
#endif

bool tactile_output_begin() {
#if ENABLE_TACTILE_OUTPUT
  bool dacOk = true;
#if ENABLE_MCP4725
  dacOk = mcp4725_begin();
#endif

  for (int i = 0; i < PWM_TACTILE_COUNT; i++) {
    int pin = PWM_TACTILE_PINS[i];
    ledcAttach(pin, PWM_FREQUENCY, PWM_RESOLUTION);
    ledcWrite(pin, 0);
    serialDebugPrintf("PWM tactile Pin_%c GPIO %d (shake %.0f Hz, drive %.2f)\n", 'A' + i,
                      pin, (double)s_carrierHz, (double)PWM_TACTILE_DRIVE);
  }

  const esp_timer_create_args_t timerArgs = {
      .callback = &tactileCarrierTick,
      .arg = nullptr,
      .dispatch_method = ESP_TIMER_TASK,
      .name = "tactile_pwm",
      .skip_unhandled_events = true,
  };
  if (esp_timer_create(&timerArgs, &s_timer) != ESP_OK) {
    return false;
  }
  const uint64_t periodUs = 1000000ULL / (uint64_t)PWM_TACTILE_UPDATE_HZ;
  if (esp_timer_start_periodic(s_timer, periodUs) != ESP_OK) {
    return false;
  }
  return dacOk;
#else
  return false;
#endif
}

void tactile_output_set_level(int pinIndex, float level01) {
  if (pinIndex < 0 || pinIndex >= MAX_PINS) {
    return;
  }
  if (level01 < 0.0f) level01 = 0.0f;
  if (level01 > 1.0f) level01 = 1.0f;
  float cap = TACTILE_MAX_LEVEL[pinIndex];
  if (cap < 0.0f) cap = 0.0f;
  if (cap > 1.0f) cap = 1.0f;
  if (level01 > cap) level01 = cap;
  s_levels[pinIndex] = level01;
}

void tactile_output_apply(bool active) {
#if !ENABLE_TACTILE_OUTPUT
  (void)active;
  return;
#endif
  s_active = active;
}

void tactile_output_set_carrier_hz(float hz) {
  if (hz < 15.0f) hz = 15.0f;
  if (hz > 200.0f) hz = 200.0f;
  s_carrierHz = hz;
}

float tactile_output_get_carrier_hz() { return s_carrierHz; }

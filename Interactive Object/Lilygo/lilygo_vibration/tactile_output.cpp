#include "tactile_output.h"
#include "settings.h"
#if ENABLE_MCP4725
#include "mcp4725.h"
#endif

static float s_levels[MAX_PINS] = {0};
static int s_pwmDuty[MAX_PINS] = {0};

static int levelToPwmDuty(float level01) {
  if (level01 < 0.0f) level01 = 0.0f;
  if (level01 > 1.0f) level01 = 1.0f;
  int duty = (int)(level01 * (float)(PWM_MAX - PWM_MIN) + (float)PWM_MIN);
  return constrain(duty, PWM_MIN, PWM_MAX);
}

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
    Serial.printf("PWM tactile Pin_%c GPIO %d (+ external RC to amplifier)\n", 'A' + i, pin);
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
  // Per-channel safety ceiling (protects lower-power exciters, e.g. 5W DAEX19CT-4)
  float cap = TACTILE_MAX_LEVEL[pinIndex];
  if (cap < 0.0f) cap = 0.0f;
  if (cap > 1.0f) cap = 1.0f;
  if (level01 > cap) level01 = cap;
  s_levels[pinIndex] = level01;
  s_pwmDuty[pinIndex] = levelToPwmDuty(level01);
}

void tactile_output_apply(bool active) {
#if !ENABLE_TACTILE_OUTPUT
  (void)active;
  return;
#endif

  for (int pin = 0; pin < MAX_PINS; pin++) {
    const TactileRoute& route = TACTILE_ROUTES[pin];
    float level = active ? s_levels[pin] : 0.0f;

    if (route.type == TACTILE_ROUTE_MCP4725) {
#if ENABLE_MCP4725
      if (route.index < MCP4725_COUNT) {
        mcp4725_write_level(route.index, level);
      }
#endif
    } else if (route.type == TACTILE_ROUTE_PWM) {
      if (route.index < PWM_TACTILE_COUNT) {
        int gpio = PWM_TACTILE_PINS[route.index];
        int duty = active ? s_pwmDuty[pin] : 0;
        ledcWrite(gpio, duty);
      }
    }
  }
}

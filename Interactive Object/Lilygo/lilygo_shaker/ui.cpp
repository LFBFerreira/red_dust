#include "ui.h"
#include "helpers.h"

#include <math.h>
#if ACTIVE_BOARD == BOARD_TTGO_T_DISPLAY
#include <TFT_eSPI.h>
#include <TFT_eWidget.h>
#endif

static float s_lastSnapshot[MAX_PINS] = {NAN};
static bool s_lastReceiving = false;
static String s_lastWifiStatusText = "";

static bool pinsChangedSinceSnapshot(const float* pinValues) {
  for (int i = 0; i < MAX_PINS; i++) {
    if (isnan(s_lastSnapshot[i]) || fabs(pinValues[i] - s_lastSnapshot[i]) > 0.0001f) {
      return true;
    }
  }
  return false;
}

static void captureSnapshot(const float* pinValues, const String& wifiStatusText, bool receiving) {
  s_lastReceiving = receiving;
  for (int i = 0; i < MAX_PINS; i++) {
    s_lastSnapshot[i] = pinValues[i];
  }
  s_lastWifiStatusText = wifiStatusText;
}

static void resetUiSnapshot() {
  for (int i = 0; i < MAX_PINS; i++) {
    s_lastSnapshot[i] = NAN;
  }
  s_lastReceiving = false;
  s_lastWifiStatusText = "";
}

static bool statusNeedsUpdate(const float* pins, bool streamActive, const String& wifiStatusText) {
  return streamActive != s_lastReceiving || pinsChangedSinceSnapshot(pins) ||
         wifiStatusText != s_lastWifiStatusText;
}

static void logStatusLine(const String& wifiStatusText, bool streamActive, const float* pins) {
  const char* outPath =
#if ENABLE_I2S_PCM5102
      "PCM5102";
#elif ENABLE_TACTILE_OUTPUT
      "PWM";
#else
      "off";
#endif
  serialDebugPrintf("[status] %s | %s | %s | A=%.3f B=%.3f C=%.3f D=%.3f\n", wifiStatusText.c_str(),
                    streamActive ? "Active" : "Idle", outPath, pins[0], pins[1], pins[2], pins[3]);
}

#if ACTIVE_BOARD == BOARD_TTGO_T_DISPLAY

static TFT_eSPI s_tft = TFT_eSPI();
static GraphWidget s_gr = GraphWidget(&s_tft);
static TraceWidget s_pinTrace0(&s_gr);
static TraceWidget s_pinTrace1(&s_gr);
static TraceWidget s_pinTrace2(&s_gr);
static TraceWidget s_pinTrace3(&s_gr);
static TraceWidget s_pinTrace4(&s_gr);
static TraceWidget s_pinTrace5(&s_gr);
static TraceWidget* const s_pinTraces[MAX_PINS] = {
    &s_pinTrace0, &s_pinTrace1, &s_pinTrace2, &s_pinTrace3, &s_pinTrace4, &s_pinTrace5};
static const uint16_t TRACE_COLORS[MAX_PINS] = {TFT_RED,  TFT_GREEN,  TFT_YELLOW,
                                                TFT_CYAN, TFT_MAGENTA, TFT_WHITE};

static const float gxLow = 0.0f;
static const float gxHigh = 200.0f;
static const float gyLow = 0.0f;
static const float gyHigh = 10.0f;
static float s_graphX = 0.0f;
static bool s_graphInitialized = false;

static void restartGraphTraces() {
  if (!s_graphInitialized) {
    return;
  }
  s_gr.drawGraph(10, 25);
  for (int i = 0; i < MAX_PINS; i++) {
    s_pinTraces[i]->startTrace(TRACE_COLORS[i]);
  }
}

void ui_begin() {
  pinMode(4, OUTPUT);
  digitalWrite(4, HIGH);
  serialDebugPrintln("Backlight: GPIO 4 HIGH");

  s_tft.init();
  s_tft.setRotation(3);
#if DISPLAY_BOOT_TEST
  s_tft.fillScreen(TFT_RED);
  delay(400);
#endif
  s_tft.fillScreen(TFT_BLACK);

  s_gr.createGraph(220, 100, s_tft.color565(5, 5, 5));
  s_gr.setGraphScale(gxLow, gxHigh, gyLow, gyHigh);
  s_gr.setGraphGrid(gxLow, 1000, gyLow, 2, GRAPH_GRID_COLOR);
  s_gr.drawGraph(10, 25);
  for (int i = 0; i < MAX_PINS; i++) {
    s_pinTraces[i]->startTrace(TRACE_COLORS[i]);
  }

  s_graphInitialized = true;
  s_graphX = 0.0f;
  resetUiSnapshot();
  ui_update(nullptr, false);
  serialDebugPrintln("TFT display and graph initialized (multi-pin overlay)");
}

void ui_onPinFrame(const float* pinValues, const bool* slotLive, int incomingCount) {
  if (!s_graphInitialized || pinValues == nullptr || slotLive == nullptr) {
    return;
  }

  static int sLastIncomingCount = -1;
  if (sLastIncomingCount >= 0 && incomingCount < sLastIncomingCount) {
    restartGraphTraces();
  }
  sLastIncomingCount = incomingCount;

  for (int i = 0; i < incomingCount && i < MAX_PINS; i++) {
    if (!slotLive[i]) {
      continue;
    }
    s_pinTraces[i]->addPoint(s_graphX, pinValues[i] * 10.0f);
  }
  s_graphX += 1.0f;
  if (s_graphX > gxHigh) {
    s_graphX = 0.0f;
    restartGraphTraces();
  }
}

void ui_update(const float* pinValues, bool streamActive) {
  float zeros[MAX_PINS] = {0};
  const float* pins = (pinValues != nullptr) ? pinValues : zeros;

  String wifiStatusText;
  int wifiStatusColor = TFT_WHITE;
  wifiStatusLabel(&wifiStatusText, &wifiStatusColor);

  if (!statusNeedsUpdate(pins, streamActive, wifiStatusText)) {
    return;
  }

  logStatusLine(wifiStatusText, streamActive, pins);

  float displayValue = constrain(pins[0], 0.0f, 1.0f);
  s_tft.setTextFont(2);
  s_tft.setTextSize(1);
  s_tft.fillRect(0, 0, 240, 20, TFT_BLACK);

  s_tft.setCursor(5, 5);
  s_tft.setTextColor(wifiStatusColor, TFT_BLACK, true);
  s_tft.print(wifiStatusText);

  s_tft.setCursor(120, 5);
  s_tft.setTextColor(streamActive ? TFT_CYAN : TFT_YELLOW, TFT_BLACK, true);
  s_tft.print(streamActive ? "Active" : "Idle");

  s_tft.setCursor(190, 5);
  s_tft.setTextColor(TFT_WHITE, TFT_BLACK, true);
  s_tft.print(displayValue, 3);

  captureSnapshot(pins, wifiStatusText, streamActive);
}

#else  // DevKitC-1 — no TFT

void ui_begin() {
  // Do not touch GPIO4 (PWM Pin_A on this board).
  resetUiSnapshot();
}

void ui_onPinFrame(const float* /*pinValues*/, const bool* /*slotLive*/, int /*incomingCount*/) {}

void ui_update(const float* pinValues, bool streamActive) {
  float zeros[MAX_PINS] = {0};
  const float* pins = (pinValues != nullptr) ? pinValues : zeros;

  String wifiStatusText;
  int wifiStatusColor = 0;
  wifiStatusLabel(&wifiStatusText, &wifiStatusColor);

  if (!statusNeedsUpdate(pins, streamActive, wifiStatusText)) {
    return;
  }

  logStatusLine(wifiStatusText, streamActive, pins);
  captureSnapshot(pins, wifiStatusText, streamActive);
}

#endif

#if ACTIVE_BOARD == BOARD_ESP32_S3_DEVKITC_1

static uint8_t s_statusLedR = 255;
static uint8_t s_statusLedG = 255;
static uint8_t s_statusLedB = 255;

void ui_statusLedInvalidate() {
  s_statusLedR = 255;
  s_statusLedG = 255;
  s_statusLedB = 255;
}

static void statusRgbWrite(uint8_t r, uint8_t g, uint8_t b) {
  if (r == s_statusLedR && g == s_statusLedG && b == s_statusLedB) {
    return;
  }
  s_statusLedR = r;
  s_statusLedG = g;
  s_statusLedB = b;
  neopixelWrite(STATUS_RGB_LED_PIN, r, g, b);
}

void ui_statusLedBootTest() {
  neopixelWrite(STATUS_RGB_LED_PIN, 0, 0, 0);
  delay(50);
  neopixelWrite(STATUS_RGB_LED_PIN, 255, 0, 0);
  delay(200);
  neopixelWrite(STATUS_RGB_LED_PIN, 0, 255, 0);
  delay(200);
  neopixelWrite(STATUS_RGB_LED_PIN, 0, 0, 255);
  delay(200);
  neopixelWrite(STATUS_RGB_LED_PIN, 0, 0, 0);
  ui_statusLedInvalidate();
}

void ui_statusLedShowIdle() { statusRgbWrite(255, 0, 0); }

void ui_statusLedUpdate(bool streamActive, float pinALevel) {
  if (!streamActive) {
    ui_statusLedShowIdle();
    return;
  }
  uint8_t blue = (uint8_t)(constrain(pinALevel, 0.0f, 1.0f) * 255.0f);
  if (blue < 16) {
    blue = 16;
  }
  statusRgbWrite(0, 0, blue);
}

#endif

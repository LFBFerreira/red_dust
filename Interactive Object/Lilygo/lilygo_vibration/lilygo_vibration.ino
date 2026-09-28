#include "settings.h"
#include "i2s_audio.h"
#include "tactile_output.h"

#include <TFT_eSPI.h>
#include <TFT_eWidget.h>
#include <FS.h>
using fs::FS;
#include <WiFi.h>
#include <WiFiUdp.h>
#include <WiFiManager.h>
#include <string.h>
#include <math.h>

// ---------------------------------------------------------------------------
// Globals
// ---------------------------------------------------------------------------

TFT_eSPI tft = TFT_eSPI();
WiFiManager wm;
WiFiUDP udp;

GraphWidget gr = GraphWidget(&tft);
TraceWidget pinTrace0(&gr);
TraceWidget pinTrace1(&gr);
TraceWidget pinTrace2(&gr);
TraceWidget pinTrace3(&gr);
TraceWidget pinTrace4(&gr);
TraceWidget pinTrace5(&gr);
TraceWidget* const pinTraces[MAX_PINS] = {&pinTrace0, &pinTrace1, &pinTrace2,
                                          &pinTrace3, &pinTrace4, &pinTrace5};
static const uint16_t TRACE_COLORS[MAX_PINS] = {TFT_RED,  TFT_GREEN,  TFT_YELLOW,
                                                TFT_CYAN, TFT_MAGENTA, TFT_WHITE};

static const float gxLow = 0.0f;
static const float gxHigh = 200.0f;
static const float gyLow = 0.0f;
static const float gyHigh = 10.0f;
static float graphX = 0.0f;
static bool graphInitialized = false;

static float latestPinValues[MAX_PINS] = {0};
static float lastSnapshotForGui[MAX_PINS] = {NAN};
static float latestValue = 0.0f;  // Pin_A (status bar)

static bool lastSerialConnected = false;
static bool lastSerialReceiving = false;
static bool lastOscReceiving = false;
static float lastDisplayedValue = -1.0f;
static bool wifiConnected = false;
static bool lastWifiConnected = false;
static String lastWifiStatusText = "";

static String serialBuffer = "";
static const int SERIAL_BUFFER_SIZE = 384;
static const unsigned long SERIAL_TIMEOUT_MS = 1000;
static unsigned long lastSerialCharTime = 0;
static bool serialConnected = false;
static bool serialReceivingData = false;

static const int OSC_BUFFER_SIZE = 512;
static uint8_t oscBuffer[OSC_BUFFER_SIZE];
static bool oscReceivingData = false;
static unsigned long lastOscTime = 0;

static bool hasLiveData = false;

enum DataSource { SOURCE_SERIAL, SOURCE_OSC };

// ---------------------------------------------------------------------------
// Small helpers
// ---------------------------------------------------------------------------

static int alignTo4Bytes(int offset) { return (offset + 3) & ~3; }

static bool isStreamActive() { return serialReceivingData || oscReceivingData; }

// Exact 0 stays off; (0,1] -> [SHAKE_LEVEL_FLOOR, 1] so small OSC still moves the shaker.
static float scaleShakeLevel(float level01) {
  if (!(level01 > 0.0f)) {
    return 0.0f;
  }
  if (level01 >= 1.0f) {
    return 1.0f;
  }
  return SHAKE_LEVEL_FLOOR + level01 * (1.0f - SHAKE_LEVEL_FLOOR);
}

static bool sanitizeLevel01(float* v) {
  if (v == nullptr || isnan(*v) || isinf(*v) || *v < 0.0f || *v > 1.0f) {
    return false;
  }
  *v = constrain(*v, 0.0f, 1.0f);
  return true;
}

static bool parseFloatToken(const String& token, float* out) {
  if (token.length() == 0) {
    *out = 0.0f;
    return false;
  }
  float v = token.toFloat();
  if (isnan(v) || isinf(v)) {
    *out = 0.0f;
    return false;
  }
  *out = v;
  return true;
}

// "FREQ,32" / "FREQ=32" -> hz; returns false if not this command or invalid.
static bool parsePrefixedIntCommand(const String& message, const char* key, int* outHz) {
  String msg = message;
  msg.trim();
  const size_t keyLen = strlen(key);
  if (msg.length() <= (int)keyLen + 1) {
    return false;
  }
  if (!msg.startsWith(key)) {
    return false;
  }
  char sep = msg.charAt(keyLen);
  if (sep != ',' && sep != '=') {
    return false;
  }
  String rest = msg.substring(keyLen + 1);
  rest.trim();
  if (rest.length() == 0) {
    return false;
  }
  int hz = rest.toInt();
  if (hz <= 0) {
    return false;
  }
  *outHz = hz;
  return true;
}

static void clearLivePinValues() {
  for (int i = 0; i < MAX_PINS; i++) {
    latestPinValues[i] = 0.0f;
  }
  latestValue = 0.0f;
  hasLiveData = false;
}

static void pushOutputs() {
#if ENABLE_TACTILE_OUTPUT
  for (int i = 0; i < MAX_PINS; i++) {
    tactile_output_set_level(i, scaleShakeLevel(latestPinValues[i]));
  }
  tactile_output_apply(hasLiveData);
#endif
#if ENABLE_I2S_PCM5102
  if (hasLiveData) {
    i2s_audio_set_stereo_levels(scaleShakeLevel(latestPinValues[I2S_LEFT_PIN_INDEX]),
                                scaleShakeLevel(latestPinValues[I2S_RIGHT_PIN_INDEX]));
  } else {
    i2s_audio_mute();
  }
#endif
}

static void captureGuiSnapshot(const String& wifiStatusText) {
  lastSerialConnected = serialConnected;
  lastSerialReceiving = serialReceivingData;
  lastOscReceiving = oscReceivingData;
  lastDisplayedValue = latestValue;
  for (int i = 0; i < MAX_PINS; i++) {
    lastSnapshotForGui[i] = latestPinValues[i];
  }
  lastWifiStatusText = wifiStatusText;
  lastWifiConnected = wifiConnected;
}

static void restartGraphTraces() {
  if (!graphInitialized) {
    return;
  }
  gr.drawGraph(10, 25);
  for (int i = 0; i < MAX_PINS; i++) {
    pinTraces[i]->startTrace(TRACE_COLORS[i]);
  }
}

static void setShakeCarrierHz(float hz) {
#if ENABLE_I2S_PCM5102
  i2s_audio_set_carrier_hz(hz);
  serialDebugPrintf("PCM5102 carrier fixed to %.0f Hz (OSC still scales volume)\n", (double)hz);
#endif
#if ENABLE_TACTILE_OUTPUT
  tactile_output_set_carrier_hz(hz);
  serialDebugPrintf("PWM tactile carrier set to %.0f Hz\n",
                    (double)tactile_output_get_carrier_hz());
#endif
}

// ---------------------------------------------------------------------------
// Output / frame path
// ---------------------------------------------------------------------------

static void silenceOutputsOnStreamIdle() {
  if (isStreamActive() || !hasLiveData) {
    return;
  }
  clearLivePinValues();
  pushOutputs();
}

// Apply one frame: incoming[0..count-1]; [0,1] = live; out of range = inactive.
static void applyPinFrame(const float* incoming, int incomingCount, DataSource source) {
  if (incomingCount < 0) incomingCount = 0;
  if (incomingCount > MAX_PINS) incomingCount = MAX_PINS;

  if (source == SOURCE_OSC) {
    oscReceivingData = true;
    lastOscTime = millis();
  }

  bool slotLive[MAX_PINS] = {false};
  for (int i = 0; i < MAX_PINS; i++) {
    float v = (incoming != nullptr && i < incomingCount) ? incoming[i] : 0.0f;
    if (!sanitizeLevel01(&v)) {
      latestPinValues[i] = 0.0f;
      slotLive[i] = false;
      continue;
    }
    slotLive[i] = true;
    latestPinValues[i] = v;
  }
  hasLiveData = true;
  latestValue = latestPinValues[0];
  pushOutputs();

  if (!graphInitialized) {
    return;
  }

  static int sLastIncomingCount = -1;
  if (sLastIncomingCount >= 0 && incomingCount < sLastIncomingCount) {
    restartGraphTraces();
  }
  sLastIncomingCount = incomingCount;

  for (int i = 0; i < incomingCount && i < MAX_PINS; i++) {
    if (!slotLive[i]) continue;
    pinTraces[i]->addPoint(graphX, latestPinValues[i] * 10.0f);
  }
  graphX += 1.0f;
  if (graphX > gxHigh) {
    graphX = 0.0f;
    restartGraphTraces();
  }
}

// ---------------------------------------------------------------------------
// Serial
// ---------------------------------------------------------------------------

static bool processControlMessage(const String& message) {
  int hz = 0;
  if (!parsePrefixedIntCommand(message, "FREQ", &hz)) {
    return false;
  }
  setShakeCarrierHz((float)hz);
  return true;
}

// Line: v1,v2,...,vN,timestamp  (last comma separates timestamp)
static void processSerialMessage(const String& message) {
  if (processControlMessage(message)) {
    return;
  }

  int lastComma = message.lastIndexOf(',');
  if (lastComma <= 0 || lastComma >= (int)message.length() - 1) {
    return;
  }

  String timestamp = message.substring(lastComma + 1);
  timestamp.trim();
  if (timestamp.length() == 0) {
    return;
  }

  String valuesPart = message.substring(0, lastComma);
  valuesPart.trim();
  if (valuesPart.length() == 0) {
    return;
  }

  float values[MAX_PINS];
  int n = 0;
  int start = 0;
  for (int i = 0; i <= (int)valuesPart.length(); i++) {
    if (i == (int)valuesPart.length() || valuesPart.charAt(i) == ',') {
      String token = valuesPart.substring(start, i);
      token.trim();
      if (token.length() > 0 && n < MAX_PINS) {
        float v;
        parseFloatToken(token, &v);
        values[n++] = v;
      }
      start = i + 1;
    }
  }
  if (n == 0) {
    return;
  }

  serialReceivingData = true;
  lastSerialCharTime = millis();
  applyPinFrame(values, n, SOURCE_SERIAL);
}

static void processSerialMessages() {
  if (Serial.available() > 0) {
    lastSerialCharTime = millis();
    serialConnected = true;
    serialReceivingData = true;

    while (Serial.available() > 0) {
      char c = Serial.read();
      if (c == '\n' || c == '\r') {
        serialBuffer += '\n';
      } else if (c >= 32 && c <= 126) {
        serialBuffer += c;
        if ((int)serialBuffer.length() >= SERIAL_BUFFER_SIZE - 1) {
          serialBuffer = "";
        }
      }
    }

    int lastNewline = serialBuffer.lastIndexOf('\n');
    if (lastNewline >= 0) {
      int messageStart = 0;
      for (int i = lastNewline - 1; i >= 0; i--) {
        if (serialBuffer.charAt(i) == '\n') {
          messageStart = i + 1;
          break;
        }
      }
      String latestMessage = serialBuffer.substring(messageStart, lastNewline);
      if (latestMessage.length() > 0) {
        processSerialMessage(latestMessage);
      }
      serialBuffer = (lastNewline < (int)serialBuffer.length() - 1)
                         ? serialBuffer.substring(lastNewline + 1)
                         : String("");
    }
  }

  if (serialReceivingData && (millis() - lastSerialCharTime) > STREAM_IDLE_TIMEOUT_MS) {
    serialReceivingData = false;
  }
  if (serialBuffer.length() > 0 && (millis() - lastSerialCharTime) > SERIAL_TIMEOUT_MS) {
    serialBuffer = "";
  }
}

// ---------------------------------------------------------------------------
// OSC
// ---------------------------------------------------------------------------

// Typetag ,f...fs (>=0 floats, then timestamp string). Path must match OSC_PATH.
static bool parseOSCMessageMulti(uint8_t* buffer, int packetSize, float* outValues,
                                 int maxValues, int* outFloatCount) {
  *outFloatCount = 0;
  if (packetSize < 8) return false;

  int offset = 0;
  const char* oscPath = OSC_PATH;
  int oscPathLen = strlen(oscPath);
  int pathLen = 0;
  while (offset + pathLen < packetSize && buffer[offset + pathLen] != 0) {
    pathLen++;
  }
  if (pathLen != oscPathLen || memcmp(buffer + offset, oscPath, pathLen) != 0) {
    return false;
  }

  offset = alignTo4Bytes(offset + pathLen + 1);
  if (offset >= packetSize || buffer[offset] != ',') return false;

  int p = offset + 1;
  int fCount = 0;
  while (p < packetSize && buffer[p] == 'f') {
    fCount++;
    p++;
  }
  if (p >= packetSize || buffer[p] != 's') return false;
  p++;
  while (p < packetSize && buffer[p] != 0) {
    p++;
  }
  if (p >= packetSize) return false;
  offset = alignTo4Bytes(p + 1);

  for (int fi = 0; fi < fCount; fi++) {
    if (offset + 4 > packetSize) return false;
    union {
      uint8_t bytes[4];
      float val;
    } u;
    u.bytes[3] = buffer[offset];
    u.bytes[2] = buffer[offset + 1];
    u.bytes[1] = buffer[offset + 2];
    u.bytes[0] = buffer[offset + 3];
    offset += 4;
    if (fi < maxValues) {
      outValues[fi] = u.val;
    }
  }

  if (offset >= packetSize) return false;
  while (offset < packetSize && buffer[offset] != 0) {
    offset++;
  }
  if (offset >= packetSize) return false;
  offset = alignTo4Bytes(offset + 1);

  *outFloatCount = fCount;
  return true;
}

static void processOSCMessages() {
  if (WiFi.status() != WL_CONNECTED) {
    return;
  }

  int latestPacketSize = 0;
  int packetCount = 0;
  while (true) {
    int packetSize = udp.parsePacket();
    if (packetSize <= 0) break;
    packetCount++;
    if (packetSize > OSC_BUFFER_SIZE) {
      serialDebugPrintf("OSC packet too large: %d bytes\n", packetSize);
      while (udp.available()) udp.read();
      continue;
    }
    int len = udp.read(oscBuffer, OSC_BUFFER_SIZE);
    if (len > 0) {
      latestPacketSize = len;
    }
  }

  if (latestPacketSize > 0) {
    oscReceivingData = true;
    lastOscTime = millis();

    float oscVals[MAX_PINS];
    int fcnt = 0;
    if (parseOSCMessageMulti(oscBuffer, latestPacketSize, oscVals, MAX_PINS, &fcnt)) {
      applyPinFrame(oscVals, (fcnt < MAX_PINS) ? fcnt : MAX_PINS, SOURCE_OSC);
    } else {
      serialDebugPrintln("Failed to parse OSC message");
    }
    if (packetCount > 1) {
      serialDebugPrintf("Discarded %d OSC packets, processed latest\n", packetCount - 1);
    }
  }

  if (oscReceivingData && (millis() - lastOscTime) > STREAM_IDLE_TIMEOUT_MS) {
    oscReceivingData = false;
  }
}

// ---------------------------------------------------------------------------
// GUI / status LED
// ---------------------------------------------------------------------------

static void updateGui() {
  String wifiStatusText;
  int wifiStatusColor = TFT_WHITE;

  if (WiFi.status() == WL_CONNECTED) {
    wifiStatusText = WiFi.localIP().toString();
    wifiStatusColor = TFT_GREEN;
  } else if (WiFi.getMode() == WIFI_AP || WiFi.getMode() == WIFI_AP_STA) {
    wifiStatusText = "Config: " + WiFi.softAPIP().toString();
    wifiStatusColor = TFT_YELLOW;
  } else {
    String ssid = WiFi.SSID();
    wifiStatusText = (ssid.length() > 0) ? ("Connecting: " + ssid) : String("Connecting...");
    wifiStatusColor = TFT_CYAN;
  }
  if (wifiStatusText.length() > 14) {
    wifiStatusText = wifiStatusText.substring(0, 11) + "...";
  }

  bool pinsChanged = false;
  for (int i = 0; i < MAX_PINS; i++) {
    if (isnan(lastSnapshotForGui[i]) ||
        fabs(latestPinValues[i] - lastSnapshotForGui[i]) > 0.0001f) {
      pinsChanged = true;
      break;
    }
  }

  const bool receiving = isStreamActive();
  const bool needsUpdate =
      serialConnected != lastSerialConnected || serialReceivingData != lastSerialReceiving ||
      oscReceivingData != lastOscReceiving || pinsChanged || wifiStatusText != lastWifiStatusText ||
      wifiConnected != lastWifiConnected || fabs(latestValue - lastDisplayedValue) > 0.0001f;
  if (!needsUpdate) {
    return;
  }

  const char* outPath =
#if ENABLE_I2S_PCM5102
      "PCM5102";
#elif ENABLE_TACTILE_OUTPUT
      "PWM";
#else
      "off";
#endif
  serialDebugPrintf("[status] %s | %s | %s | A=%.3f B=%.3f C=%.3f D=%.3f\n", wifiStatusText.c_str(),
                    receiving ? "Active" : "Idle", outPath, latestPinValues[0], latestPinValues[1],
                    latestPinValues[2], latestPinValues[3]);

#if ACTIVE_BOARD != BOARD_TTGO_T_DISPLAY
  captureGuiSnapshot(wifiStatusText);
  return;
#else
  float displayValue = constrain(latestValue, 0.0f, 1.0f);

  tft.setTextFont(2);
  tft.setTextSize(1);
  tft.fillRect(0, 0, 240, 20, TFT_BLACK);

  tft.setCursor(5, 5);
  tft.setTextColor(wifiStatusColor, TFT_BLACK, true);
  tft.print(wifiStatusText);

  tft.setCursor(120, 5);
  tft.setTextColor(receiving ? TFT_CYAN : TFT_YELLOW, TFT_BLACK, true);
  tft.print(receiving ? "Active" : "Idle");

  tft.setCursor(190, 5);
  tft.setTextColor(TFT_WHITE, TFT_BLACK, true);
  tft.print(displayValue, 3);

  captureGuiSnapshot(wifiStatusText);
#endif
}

#if ENABLE_STATUS_RGB_LED
static uint8_t s_statusLedR = 255;
static uint8_t s_statusLedG = 255;
static uint8_t s_statusLedB = 255;

// WiFi/RMT can blank the WS2812 without updating our cache; force the next write.
static void statusRgbInvalidate() {
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

static void statusRgbBootTest() {
  neopixelWrite(STATUS_RGB_LED_PIN, 0, 0, 0);
  delay(50);
  neopixelWrite(STATUS_RGB_LED_PIN, 255, 0, 0);
  delay(200);
  neopixelWrite(STATUS_RGB_LED_PIN, 0, 255, 0);
  delay(200);
  neopixelWrite(STATUS_RGB_LED_PIN, 0, 0, 255);
  delay(200);
  neopixelWrite(STATUS_RGB_LED_PIN, 0, 0, 0);
  statusRgbInvalidate();
}

static void statusRgbShowIdle() { statusRgbWrite(255, 0, 0); }

static void updateStatusRgbLed() {
  if (!isStreamActive()) {
    statusRgbShowIdle();
    return;
  }
  uint8_t blue = (uint8_t)(constrain(latestPinValues[0], 0.0f, 1.0f) * 255.0f);
  if (blue < 16) blue = 16;
  statusRgbWrite(0, 0, blue);
}
#endif

// ---------------------------------------------------------------------------
// Init
// ---------------------------------------------------------------------------

static void initializeDisplay() {
#if ACTIVE_BOARD == BOARD_TTGO_T_DISPLAY
  pinMode(4, OUTPUT);
  digitalWrite(4, HIGH);
  serialDebugPrintln("Backlight: GPIO 4 HIGH");

  tft.init();
  tft.setRotation(3);
#if DISPLAY_BOOT_TEST
  tft.fillScreen(TFT_RED);
  delay(400);
#endif
  tft.fillScreen(TFT_BLACK);

  gr.createGraph(220, 100, tft.color565(5, 5, 5));
  gr.setGraphScale(gxLow, gxHigh, gyLow, gyHigh);
  gr.setGraphGrid(gxLow, 1000, gyLow, 2, GRAPH_GRID_COLOR);
  gr.drawGraph(10, 25);
  for (int i = 0; i < MAX_PINS; i++) {
    pinTraces[i]->startTrace(TRACE_COLORS[i]);
  }

  graphInitialized = true;
  graphX = 0.0f;
  clearLivePinValues();
  for (int i = 0; i < MAX_PINS; i++) {
    lastSnapshotForGui[i] = NAN;
  }
  lastSerialConnected = false;
  lastSerialReceiving = false;
  lastOscReceiving = false;
  lastDisplayedValue = -1.0f;
  lastWifiConnected = false;
  lastWifiStatusText = "";
  wifiConnected = false;

  updateGui();
  serialDebugPrintln("TFT display and graph initialized (multi-pin overlay)");
#else
  // DevKitC-1 has no TFT; do not touch GPIO4 (PWM Pin_A on that board).
  graphInitialized = false;
#endif
}

static void initializeWiFi() {
  WiFi.mode(WIFI_STA);
  wm.setConfigPortalBlocking(false);
  wm.setConfigPortalTimeout(300);
  wm.setConnectTimeout(5);
  wm.setSaveConnectTimeout(10);

  if (wm.autoConnect("Red_Dust_Object")) {
    serialDebugPrintln("WiFi connected immediately");
    serialDebugPrintf("OSC listening on UDP port %d, path: %s (multi-float + timestamp)\n",
                      OSC_PORT, OSC_PATH);
    wifiConnected = true;
    udp.begin(OSC_PORT);
  } else {
    serialDebugPrintln("WiFi connection attempt started (non-blocking)");
    wifiConnected = false;
  }
}

static void updateWiFiStatus() {
  bool connected = (WiFi.status() == WL_CONNECTED);
  if (connected == wifiConnected) {
    return;
  }
  wifiConnected = connected;
  if (wifiConnected) {
    serialDebugPrintln("WiFi connected");
    serialDebugPrintf("OSC listening on UDP port %d, path: %s\n", OSC_PORT, OSC_PATH);
    udp.begin(OSC_PORT);
  } else {
    serialDebugPrintln("WiFi disconnected");
  }
}

static void initializeOutputs() {
#if ENABLE_I2S_PCM5102
  if (!i2s_audio_begin()) {
    serialDebugPrintln("WARNING: I2S/PCM5102 init failed — check wiring and pins in settings.h");
  }
#endif
#if ENABLE_TACTILE_OUTPUT
  if (!tactile_output_begin()) {
    serialDebugPrintln("WARNING: PWM tactile init failed — check PWM pins in settings.h");
  }
#endif
}

static void printBootBanner() {
  serialDebugPrintln("\nRed Dust Interactive Object (multi-pin)");
  serialDebugPrintln("Serial: v1[,v2,...],timestamp  (last comma = timestamp; up to MAX_PINS values)");
  serialDebugPrintln("OSC: base path + typetag ,f...fs + floats BE + timestamp string");
#if ENABLE_I2S_PCM5102
  serialDebugPrintf(
      "I2S -> PCM5102 shake: Pin_A=L Pin_B=R, OSC 0..1 -> volume + %.0f..%.0f Hz (C–F unused)\n",
      (double)I2S_CARRIER_HZ_MIN, (double)I2S_CARRIER_HZ_MAX);
#endif
#if ENABLE_TACTILE_OUTPUT
  serialDebugPrintf("Tactile: PWM GPIOs + %.0f Hz carrier (see settings.h)\n",
                    (double)PWM_TACTILE_CARRIER_HZ);
#endif
#if ENABLE_I2S_PCM5102 || ENABLE_TACTILE_OUTPUT
  serialDebugPrintln("Serial: FREQ,<Hz> forces fixed carrier (whiteboard)");
#endif
  serialDebugPrintln("==========================================");
}

// ---------------------------------------------------------------------------
// Arduino entry
// ---------------------------------------------------------------------------

void setup() {
  Serial.begin(SERIAL_BAUDRATE);
  delay(500);
  printBootBanner();

#if ENABLE_STATUS_RGB_LED
  statusRgbBootTest();
#endif

  initializeDisplay();
  initializeWiFi();

  serialBuffer.reserve(SERIAL_BUFFER_SIZE);
  serialConnected = false;
  serialReceivingData = false;
  clearLivePinValues();
  initializeOutputs();

  // WiFi/I2S init can blank the WS2812; set idle red after peripherals are up.
#if ENABLE_STATUS_RGB_LED
  statusRgbInvalidate();
  statusRgbShowIdle();
#endif
}

void loop() {
  processSerialMessages();
  silenceOutputsOnStreamIdle();
  wm.process();
  updateWiFiStatus();
  if (wifiConnected) {
    processOSCMessages();
  }
  updateGui();
#if ENABLE_STATUS_RGB_LED
  updateStatusRgbLed();
#endif
  delay(1);
}

// Configuration settings
#include "settings.h"
#include "i2s_audio.h"
#include "tactile_output.h"

// TFT Display includes
#include <TFT_eSPI.h>
TFT_eSPI tft = TFT_eSPI();

#include <TFT_eWidget.h>  // Widget library

// WiFi Manager includes
#include <FS.h>
using fs::FS;
#include <WiFi.h>
#include <WiFiUdp.h>
#include <WiFiManager.h>
#include <string.h>
WiFiManager wm;

GraphWidget gr = GraphWidget(&tft);
// One trace per pin slot (overlay on same graph)
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

// Graph configuration
const float gxLow = 0.0;
const float gxHigh = 200.0;
const float gyLow = 0.0;
const float gyHigh = 10.0;

float graphX = 0.0;
bool graphInitialized = false;

// Per-pin latest live values (0..1) and PWM; slots marked inactive stay at 0 here
float latestPinValues[MAX_PINS] = {0};
int pwmValues[MAX_PINS] = {0};
float lastSnapshotForGui[MAX_PINS] = {NAN};

float latestValue = 0.0;  // Pin_A for status bar (legacy behavior)
bool lastSerialConnected = false;
bool lastSerialReceiving = false;
bool lastOscReceiving = false;
float lastDisplayedValue = -1.0;

bool wifiConnected = false;
bool lastWifiConnected = false;
String lastWifiStatusText = "";

String serialBuffer = "";
const int SERIAL_BUFFER_SIZE = 384;
const unsigned long SERIAL_TIMEOUT_MS = 1000;
unsigned long lastSerialCharTime = 0;
bool serialConnected = false;
bool serialReceivingData = false;
const unsigned long SERIAL_RECEIVING_TIMEOUT = 500;

WiFiUDP udp;
const int OSC_BUFFER_SIZE = 512;
uint8_t oscBuffer[OSC_BUFFER_SIZE];
bool oscReceivingData = false;
unsigned long lastOscTime = 0;
const unsigned long OSC_RECEIVING_TIMEOUT = 500;

bool hasPWMData = false;

enum DataSource { SOURCE_SERIAL, SOURCE_OSC };

int alignTo4Bytes(int offset) { return (offset + 3) & ~3; }

int mapValueToPWM(float value) {
  value = constrain(value, 0.0f, 1.0f);
  int pwmValue = (int)(value * (PWM_MAX - PWM_MIN) + PWM_MIN);
  return constrain(pwmValue, PWM_MIN, PWM_MAX);
}

// Parse a single float token; returns false if token is not a plausible number (use 0.0)
// Control lines (USB Serial): MODE,TAC | MODE,AUD | FREQ,120
bool processControlMessage(const String& message) {
  String msg = message;
  msg.trim();
  if (msg.length() == 0) {
    return false;
  }

  if (msg.startsWith("MODE,") || msg.startsWith("MODE=")) {
    int sep = msg.indexOf(',');
    if (sep < 0) sep = msg.indexOf('=');
    if (sep > 0 && sep < (int)msg.length() - 1) {
      String modeStr = msg.substring(sep + 1);
      modeStr.trim();
      modeStr.toUpperCase();
#if ENABLE_I2S_PCM5102
      if (modeStr == "AUD" || modeStr == "AUDIO") {
        i2s_audio_set_mode(I2S_MODE_AUDIO);
        Serial.printf("PCM5102 AUDIO: tone %.1f Hz, Pin_A=L Pin_B=R envelope\n", I2S_CARRIER_HZ);
      } else if (modeStr == "TAC" || modeStr == "TACTILE") {
        i2s_audio_set_mode(I2S_MODE_TACTILE);
        i2s_audio_mute();
        Serial.println("PCM5102 muted; tactile on MCP4725 (A,B) + PWM+RC (C,D) -> HW-104");
      } else {
        Serial.println("Unknown MODE (use TAC or AUD)");
      }
#else
      Serial.println("PCM5102 disabled in settings.h");
#endif
    }
    return true;
  }

  if (msg.startsWith("FREQ,") || msg.startsWith("FREQ=")) {
    int sep = msg.indexOf(',');
    if (sep < 0) sep = msg.indexOf('=');
    if (sep > 0 && sep < (int)msg.length() - 1) {
      String fStr = msg.substring(sep + 1);
      fStr.trim();
      int hz = fStr.toInt();
      if (fStr.length() > 0 && hz > 0) {
#if ENABLE_I2S_PCM5102
        i2s_audio_set_carrier_hz((float)hz);
        Serial.printf("PCM5102 tone frequency set to %d Hz\n", hz);
#else
        Serial.println("PCM5102 disabled in settings.h");
#endif
      }
    }
    return true;
  }

  return false;
}

void updateTactileOutputs() {
#if ENABLE_TACTILE_OUTPUT
  for (int i = 0; i < MAX_PINS; i++) {
    tactile_output_set_level(i, latestPinValues[i]);
  }
  tactile_output_apply(hasPWMData);
#endif
}

void updatePcm5102FromPinValues() {
#if ENABLE_I2S_PCM5102
  if (i2s_audio_get_mode() != I2S_MODE_AUDIO) {
    return;
  }
  float left = latestPinValues[I2S_LEFT_PIN_INDEX];
  float right = latestPinValues[I2S_RIGHT_PIN_INDEX];
  i2s_audio_set_stereo_levels(left, right);
#endif
}

bool parseFloatToken(const String& token, float* out) {
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

void restartGraphTraces() {
  if (!graphInitialized) return;
  gr.drawGraph(10, 25);
  for (int i = 0; i < MAX_PINS; i++) {
    pinTraces[i]->startTrace(TRACE_COLORS[i]);
  }
}

// Apply one frame: incoming[0..incomingCount-1] from wire; [0,1] = live level;
// outside that range = inactive slot (do not treat as real control). Missing tail: 0.
void applyPinFrame(const float* incoming, int incomingCount, DataSource source) {
  if (incomingCount < 0) incomingCount = 0;
  if (incomingCount > MAX_PINS) incomingCount = MAX_PINS;

  if (source == SOURCE_OSC) {
    oscReceivingData = true;
    lastOscTime = millis();
  }

  bool slotLive[MAX_PINS] = {false};
  for (int i = 0; i < MAX_PINS; i++) {
    float v = (incoming != nullptr && i < incomingCount) ? incoming[i] : 0.0f;
    if (isnan(v) || isinf(v)) v = 0.0f;
    if (v < 0.0f || v > 1.0f) {
      latestPinValues[i] = 0.0f;
      pwmValues[i] = mapValueToPWM(0.0f);
      slotLive[i] = false;
      continue;
    }
    v = constrain(v, 0.0f, 1.0f);
    slotLive[i] = true;
    latestPinValues[i] = v;
    pwmValues[i] = mapValueToPWM(v);
  }
  hasPWMData = true;
  latestValue = latestPinValues[0];

  updateTactileOutputs();
  updatePcm5102FromPinValues();

  if (graphInitialized) {
    static int sLastIncomingCount = -1;
    if (sLastIncomingCount >= 0 && incomingCount < sLastIncomingCount) {
      restartGraphTraces();
    }
    sLastIncomingCount = incomingCount;

    // Only plot traces for slots present in this frame (typetag float count).
    // Otherwise extra traces keep advancing (often at y=0) after channel count drops.
    // Skip inactive (out-of-range) wire values so padding does not draw a trace.
    for (int i = 0; i < incomingCount && i < MAX_PINS; i++) {
      if (!slotLive[i]) continue;
      float graphValue = latestPinValues[i] * 10.0f;
      pinTraces[i]->addPoint(graphX, graphValue);
    }
    graphX += 1.0f;
    if (graphX > gxHigh) {
      graphX = 0.0f;
      restartGraphTraces();
    }
  }
}

void handleSerialFrame(const float* values, int count, const String& /*timestamp*/) {
  serialReceivingData = true;
  lastSerialCharTime = millis();
  applyPinFrame(values, count, SOURCE_SERIAL);
}

// Serial line: v1,v2,...,vN,timestamp  (last comma separates timestamp)
void processSerialMessage(const String& message) {
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
      if (token.length() > 0) {
        float v;
        parseFloatToken(token, &v);
        if (n < MAX_PINS) {
          values[n++] = v;
        }
        // ignore extra tokens beyond MAX_PINS (sender may send more)
      }
      start = i + 1;
    }
  }

  if (n == 0) {
    return;
  }

  handleSerialFrame(values, n, timestamp);
}

void processSerialMessages() {
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

      if (lastNewline < (int)serialBuffer.length() - 1) {
        serialBuffer = serialBuffer.substring(lastNewline + 1);
      } else {
        serialBuffer = "";
      }
    }
  }

  if (serialReceivingData && (millis() - lastSerialCharTime) > SERIAL_RECEIVING_TIMEOUT) {
    serialReceivingData = false;
  }

  if (serialBuffer.length() > 0 &&
      (millis() - lastSerialCharTime) > SERIAL_TIMEOUT_MS) {
    serialBuffer = "";
  }
}

bool isSerialConnected() { return serialConnected; }
bool isSerialReceiving() { return serialReceivingData; }

// OSC: typetag ,f...fs (>=0 floats, then timestamp string). Path must match OSC_PATH.
bool parseOSCMessageMulti(uint8_t* buffer, int packetSize, float* outValues, int maxValues,
                         int* outFloatCount) {
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
  if (offset >= packetSize) return false;

  if (buffer[offset] != ',') return false;

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
  p++;
  offset = alignTo4Bytes(p);

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
  offset++;
  offset = alignTo4Bytes(offset);

  *outFloatCount = fCount;
  return true;
}

void processOSCMessages() {
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
      Serial.printf("OSC packet too large: %d bytes\n", packetSize);
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
      int use = (fcnt < MAX_PINS) ? fcnt : MAX_PINS;
      applyPinFrame(oscVals, use, SOURCE_OSC);
    } else {
      Serial.println("Failed to parse OSC message");
    }

    if (packetCount > 1) {
      Serial.printf("Discarded %d OSC packets, processed latest\n", packetCount - 1);
    }
  }

  if (oscReceivingData && (millis() - lastOscTime) > OSC_RECEIVING_TIMEOUT) {
    oscReceivingData = false;
  }
}

void updateGui() {
  String wifiStatusText = "";
  int wifiStatusColor = TFT_WHITE;

  if (WiFi.status() == WL_CONNECTED) {
    wifiStatusText = WiFi.localIP().toString();
    wifiStatusColor = TFT_GREEN;
  } else if (WiFi.getMode() == WIFI_AP || WiFi.getMode() == WIFI_AP_STA) {
    wifiStatusText = "Config: " + WiFi.softAPIP().toString();
    wifiStatusColor = TFT_YELLOW;
  } else {
    String ssid = WiFi.SSID();
    if (ssid.length() > 0) {
      wifiStatusText = "Connecting: " + ssid;
    } else {
      wifiStatusText = "Connecting...";
    }
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

  bool isReceivingData = serialReceivingData || oscReceivingData;
  bool needsUpdate = false;
  if (serialConnected != lastSerialConnected || serialReceivingData != lastSerialReceiving ||
      oscReceivingData != lastOscReceiving || pinsChanged || wifiStatusText != lastWifiStatusText ||
      wifiConnected != lastWifiConnected || fabs(latestValue - lastDisplayedValue) > 0.0001f) {
    needsUpdate = true;
  }

  if (!needsUpdate) {
    return;
  }

  float displayValue = constrain(latestValue, 0.0f, 1.0f);
#if SERIAL_STATUS_DEBUG
  const char* pcmMode = "PCM-off";
#if ENABLE_I2S_PCM5102
  pcmMode = (i2s_audio_get_mode() == I2S_MODE_TACTILE) ? "PCM-mute" : "PCM-AUD";
#endif
  Serial.printf("[status] %s | %s | %s | A=%.3f B=%.3f C=%.3f D=%.3f\n", wifiStatusText.c_str(),
                isReceivingData ? "Active" : "Idle", pcmMode, latestPinValues[0],
                latestPinValues[1], latestPinValues[2], latestPinValues[3]);
#endif

  tft.setTextFont(2);
  tft.setTextSize(1);
  tft.setTextColor(TFT_WHITE, TFT_BLACK, true);

  tft.fillRect(0, 0, 240, 20, TFT_BLACK);

  tft.setCursor(5, 5);
  tft.setTextColor(wifiStatusColor, TFT_BLACK, true);
  tft.print(wifiStatusText);

  tft.setCursor(120, 5);
  if (isReceivingData) {
    tft.setTextColor(TFT_CYAN, TFT_BLACK, true);
    tft.print("Active");
  } else {
    tft.setTextColor(TFT_YELLOW, TFT_BLACK, true);
    tft.print("Idle");
  }

  tft.setCursor(190, 5);
  tft.setTextColor(TFT_WHITE, TFT_BLACK, true);
  tft.print(displayValue, 3);

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

void updateVibrationMotor() {
  updateTactileOutputs();
#if ENABLE_I2S_PCM5102
  if (!hasPWMData) {
    i2s_audio_mute();
  }
#endif
}

void initializeDisplay() {
  pinMode(4, OUTPUT);
  digitalWrite(4, HIGH);  // Backlight on first (TTGO T-Display = GPIO 4)
  Serial.println("Backlight: GPIO 4 HIGH");

  tft.init();
  tft.setRotation(3);
#if DISPLAY_BOOT_TEST
  tft.fillScreen(TFT_RED);
  delay(400);  // If you see red briefly, TFT works; if always dark, see README TFT_eSPI setup
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
  graphX = 0.0;

  latestValue = 0.0;
  for (int i = 0; i < MAX_PINS; i++) {
    latestPinValues[i] = 0.0f;
    pwmValues[i] = 0;
    lastSnapshotForGui[i] = NAN;
  }
  lastSerialConnected = false;
  lastSerialReceiving = false;
  lastOscReceiving = false;
  lastDisplayedValue = -1.0;
  lastWifiConnected = false;
  lastWifiStatusText = "";
  wifiConnected = false;

  updateGui();

  Serial.println("TFT display and graph initialized (multi-pin overlay)");
}

void initializeWiFi() {
  WiFi.mode(WIFI_STA);

  wm.setConfigPortalBlocking(false);
  wm.setConfigPortalTimeout(300);
  wm.setConnectTimeout(5);
  wm.setSaveConnectTimeout(10);

  bool wifiStarted = wm.autoConnect("Red_Dust_Object");

  if (wifiStarted) {
    Serial.println("WiFi connected immediately");
    wifiConnected = true;
    udp.begin(OSC_PORT);
    Serial.printf("OSC listening on UDP port %d, path: %s (multi-float + timestamp)\n", OSC_PORT,
                  OSC_PATH);
  } else {
    Serial.println("WiFi connection attempt started (non-blocking)");
    wifiConnected = false;
  }
}

void initializeTactileOutputs() {
#if ENABLE_TACTILE_OUTPUT
  if (!tactile_output_begin()) {
    Serial.println("WARNING: MCP4725 init failed — check I2C wiring and addresses 0x60/0x61");
  }
#endif
}

void updateWiFiStatus() {
  bool currentWifiStatus = (WiFi.status() == WL_CONNECTED);
  if (currentWifiStatus != wifiConnected) {
    wifiConnected = currentWifiStatus;
    if (wifiConnected) {
      Serial.println("WiFi connected");
      udp.begin(OSC_PORT);
      Serial.printf("OSC listening on UDP port %d, path: %s\n", OSC_PORT, OSC_PATH);
    } else {
      Serial.println("WiFi disconnected");
    }
  }
}

void setup() {
  Serial.begin(SERIAL_BAUDRATE);
  delay(500);

  Serial.println("\nRed Dust Interactive Object (multi-pin)");
  Serial.println("Serial: v1[,v2,...],timestamp  (last comma = timestamp; up to MAX_PINS values)");
  Serial.println("OSC: base path + typetag ,f...fs + floats BE + timestamp string");
#if ENABLE_I2S_AUDIO
  Serial.println("I2S -> PCM5102: Pin_A=L, Pin_B=R (TACTILE=DC level, AUDIO=tone)");
  Serial.println("Serial commands: MODE,TAC | MODE,AUD | FREQ,<Hz>");
#endif
#if ENABLE_PWM_OUTPUT
  Serial.println("Motors: Pin_C..E -> PWM GPIOs (see settings.h PWM_OUTPUT_PINS)");
#endif
  Serial.println("==========================================");

  initializeDisplay();
  initializeWiFi();

  serialBuffer.reserve(SERIAL_BUFFER_SIZE);

  serialConnected = false;
  serialReceivingData = false;
  hasPWMData = false;
  for (int i = 0; i < MAX_PINS; i++) {
    pwmValues[i] = 0;
    latestPinValues[i] = 0.0f;
  }

#if ENABLE_I2S_PCM5102
  if (!i2s_audio_begin()) {
    Serial.println("WARNING: I2S/PCM5102 init failed — check wiring and pins in settings.h");
  } else if (i2s_audio_get_mode() == I2S_MODE_TACTILE) {
    i2s_audio_mute();
  }
#endif
  initializeTactileOutputs();
}

void loop() {
  processSerialMessages();
  updateVibrationMotor();
  wm.process();
  updateWiFiStatus();
  if (wifiConnected) {
    processOSCMessages();
  }
  updateGui();
  delay(1);
}

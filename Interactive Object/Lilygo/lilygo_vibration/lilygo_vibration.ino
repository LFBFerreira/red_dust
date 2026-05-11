// Configuration settings
#include "settings.h"

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
TraceWidget* const pinTraces[MAX_PINS] = {
    &pinTrace0, &pinTrace1, &pinTrace2, &pinTrace3, &pinTrace4};

static const uint16_t TRACE_COLORS[MAX_PINS] = {
    TFT_RED, TFT_GREEN, TFT_YELLOW, TFT_CYAN, TFT_MAGENTA};

// Graph configuration
const float gxLow = 0.0;
const float gxHigh = 200.0;
const float gyLow = 0.0;
const float gyHigh = 10.0;

float graphX = 0.0;
bool graphInitialized = false;

// Per-pin latest normalized values (0..1 after clamp) and PWM
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

// Apply one frame: incoming[0..incomingCount-1] are values from wire (clamp 0..1);
// missing slots zero-filled. Updates PWM, graph, and status.
void applyPinFrame(const float* incoming, int incomingCount, DataSource source) {
  if (incomingCount < 0) incomingCount = 0;
  if (incomingCount > MAX_PINS) incomingCount = MAX_PINS;

  if (source == SOURCE_OSC) {
    oscReceivingData = true;
    lastOscTime = millis();
  }

  for (int i = 0; i < MAX_PINS; i++) {
    float v = (incoming != nullptr && i < incomingCount) ? incoming[i] : 0.0f;
    if (isnan(v) || isinf(v)) v = 0.0f;
    v = constrain(v, 0.0f, 1.0f);
    latestPinValues[i] = v;
    pwmValues[i] = mapValueToPWM(v);
  }
  hasPWMData = true;
  latestValue = latestPinValues[0];

  if (graphInitialized) {
    for (int i = 0; i < MAX_PINS; i++) {
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

  float displayValue = constrain(latestValue, 0.0f, 1.0f);
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
  for (int i = 0; i < MAX_PINS; i++) {
    int duty = hasPWMData ? pwmValues[i] : 0;
    ledcWrite(OUTPUT_PINS[i], duty);
  }
}

void initializeDisplay() {
  tft.init();
  tft.setRotation(3);
  tft.fillScreen(TFT_BLACK);

  pinMode(4, OUTPUT);
  digitalWrite(4, HIGH);

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

void initializeVibrationMotor() {
  for (int i = 0; i < MAX_PINS; i++) {
    int pin = OUTPUT_PINS[i];
    ledcAttach(pin, PWM_FREQUENCY, PWM_RESOLUTION);
    ledcWrite(pin, 0);
    Serial.printf("PWM init slot %d GPIO %d\n", i, pin);
  }
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

  initializeVibrationMotor();
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

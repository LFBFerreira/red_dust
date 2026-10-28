// Croissant — one LilyGO T-Display per station (same GPIOs on both boards).
// Set STATION_ID in settings.h (1 or 2) before upload.
// Pin on/off cues live in Croissant Control Center.

#include "settings.h"
#include "tactile_output.h"
#include "dy_hv20t.h"

#include <TFT_eSPI.h>
TFT_eSPI tft = TFT_eSPI();

#include <TFT_eWidget.h>

#include <FS.h>
using fs::FS;
#include <WiFi.h>
#include <WiFiUdp.h>
#include <WiFiManager.h>
#include <string.h>
WiFiManager wm;

GraphWidget gr = GraphWidget(&tft);
TraceWidget pinTrace0(&gr);
TraceWidget pinTrace1(&gr);
TraceWidget* const pinTraces[MAX_PINS] = {&pinTrace0, &pinTrace1};

static const uint16_t TRACE_COLORS[MAX_PINS] = {TFT_RED, TFT_GREEN};

const float gxLow = 0.0;
const float gxHigh = 200.0;
const float gyLow = 0.0;
const float gyHigh = 10.0;

float graphX = 0.0;
bool graphInitialized = false;

float latestPinValues[MAX_PINS] = {0};
int pwmValues[MAX_PINS] = {0};
float lastSnapshotForGui[MAX_PINS] = {NAN};

float latestValue = 0.0;
bool lastSerialConnected = false;
bool lastSerialReceiving = false;
bool lastOscReceiving = false;
float lastDisplayedValue = -1.0;
bool lastDyPlaying = false;

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

bool processControlMessage(const String& message) {
  String msg = message;
  msg.trim();
  if (msg.length() == 0) {
    return false;
  }

  // Same contract as dust_devil: DY,PLAY / DY,STOP / DY,VOL,0-30.
  // DY1,/DY2, are aliases; only this board's station number is accepted.
  if (msg.startsWith("DY1") || msg.startsWith("DY2")) {
    if ((msg.charAt(2) - '1') != (STATION_ID - 1)) {
      return true;
    }
  } else if (!(msg.startsWith("DY,") || msg.startsWith("DY="))) {
    return false;
  }

  if (msg.startsWith("DY,BTN")) {
    return true;
  }

  int sep = msg.indexOf(',');
  if (sep < 0) sep = msg.indexOf('=');
  if (sep > 0 && sep < (int)msg.length() - 1) {
    String cmd = msg.substring(sep + 1);
    cmd.trim();
    cmd.toUpperCase();
#if ENABLE_DY_HV20T
    if (cmd == "PLAY" || cmd == "START") {
      dy_hv20t_play();
    } else if (cmd == "STOP") {
      dy_hv20t_stop();
    } else if (cmd.startsWith("VOL,") || cmd.startsWith("VOL=")) {
      int vsep = cmd.indexOf(',');
      if (vsep < 0) vsep = cmd.indexOf('=');
      int vol = cmd.substring(vsep + 1).toInt();
      dy_hv20t_set_volume((uint8_t)constrain(vol, 0, 30));
    } else {
      Serial.println("Unknown DY command (use PLAY, STOP, or VOL,0-30)");
    }
#else
    Serial.println("DY-HV20T disabled in settings.h");
#endif
  }
  return true;
}

bool tactileOutputArmed() {
#if ENABLE_DY_HV20T && DY_GATE_TACTILE_OUTPUT
  return dy_hv20t_is_playing();
#else
  return true;
#endif
}

void updateTactileOutputs() {
#if ENABLE_TACTILE_OUTPUT
  for (int i = 0; i < MAX_PINS; i++) {
    tactile_output_set_level(i, latestPinValues[i]);
  }
  tactile_output_apply(hasPWMData && tactileOutputArmed());
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

void applyPinFrame(const float* incoming, int incomingCount, DataSource source) {
  float local[MAX_PINS];
  int offset = 0;
  if (incomingCount >= STATION_ID * PINS_PER_STATION) {
    offset = (STATION_ID - 1) * PINS_PER_STATION;
  }
  for (int i = 0; i < MAX_PINS; i++) {
    int src = offset + i;
    local[i] = (incoming != nullptr && src < incomingCount) ? incoming[src] : 0.0f;
  }
  incoming = local;
  incomingCount = MAX_PINS;

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

  if (graphInitialized) {
    static int sLastIncomingCount = -1;
    if (sLastIncomingCount >= 0 && incomingCount < sLastIncomingCount) {
      restartGraphTraces();
    }
    sLastIncomingCount = incomingCount;

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

  float values[WIRE_MAX_INCOMING];
  int n = 0;
  int start = 0;
  for (int i = 0; i <= (int)valuesPart.length(); i++) {
    if (i == (int)valuesPart.length() || valuesPart.charAt(i) == ',') {
      String token = valuesPart.substring(start, i);
      token.trim();
      if (token.length() > 0) {
        float v;
        parseFloatToken(token, &v);
        if (n < WIRE_MAX_INCOMING) {
          values[n++] = v;
        }
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
  }

  while (true) {
    int newline = serialBuffer.indexOf('\n');
    if (newline < 0) {
      break;
    }
    String message = serialBuffer.substring(0, newline);
    serialBuffer = serialBuffer.substring(newline + 1);
    message.trim();
    if (message.length() > 0) {
      processSerialMessage(message);
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

    float oscVals[WIRE_MAX_INCOMING];
    int fcnt = 0;
    if (parseOSCMessageMulti(oscBuffer, latestPacketSize, oscVals, WIRE_MAX_INCOMING, &fcnt)) {
      applyPinFrame(oscVals, fcnt, SOURCE_OSC);
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
  bool dyPlaying = false;
#if ENABLE_DY_HV20T
  dyPlaying = dy_hv20t_is_playing();
#endif
  bool needsUpdate = false;
  if (serialConnected != lastSerialConnected || serialReceivingData != lastSerialReceiving ||
      oscReceivingData != lastOscReceiving || pinsChanged || wifiStatusText != lastWifiStatusText ||
      wifiConnected != lastWifiConnected || fabs(latestValue - lastDisplayedValue) > 0.0001f ||
      dyPlaying != lastDyPlaying) {
    needsUpdate = true;
  }

  if (!needsUpdate) {
    return;
  }

  float displayValue = constrain(latestValue, 0.0f, 1.0f);
#if SERIAL_STATUS_DEBUG
  Serial.printf("[croissant S%d] %s | %s | DY=%s | A=%.3f B=%.3f\n", STATION_ID,
                wifiStatusText.c_str(), isReceivingData ? "Active" : "Idle",
                dyPlaying ? "ON" : "MUTE", latestPinValues[0], latestPinValues[1]);
#endif

  tft.setTextFont(2);
  tft.setTextSize(1);
  tft.setTextColor(TFT_WHITE, TFT_BLACK, true);

  tft.fillRect(0, 0, 240, 20, TFT_BLACK);

  tft.setCursor(5, 5);
  tft.setTextColor(wifiStatusColor, TFT_BLACK, true);
  tft.print(wifiStatusText);

  tft.setCursor(110, 5);
  if (isReceivingData) {
    tft.setTextColor(TFT_CYAN, TFT_BLACK, true);
    tft.print("Active");
  } else {
    tft.setTextColor(TFT_YELLOW, TFT_BLACK, true);
    tft.print("Idle");
  }

#if ENABLE_DY_HV20T
  tft.setCursor(155, 5);
  tft.setTextColor(dyPlaying ? TFT_GREEN : TFT_RED, TFT_BLACK, true);
  tft.printf("D%d", STATION_ID);
#endif

  tft.setCursor(190, 5);
  tft.setTextColor(TFT_WHITE, TFT_BLACK, true);
  tft.print(displayValue, 3);

  lastSerialConnected = serialConnected;
  lastSerialReceiving = serialReceivingData;
  lastOscReceiving = oscReceivingData;
  lastDisplayedValue = latestValue;
  lastDyPlaying = dyPlaying;
  for (int i = 0; i < MAX_PINS; i++) {
    lastSnapshotForGui[i] = latestPinValues[i];
  }
  lastWifiStatusText = wifiStatusText;
  lastWifiConnected = wifiConnected;
}

void initializeDisplay() {
  pinMode(4, OUTPUT);
  digitalWrite(4, HIGH);
  Serial.println("Backlight: GPIO 4 HIGH");

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
  lastDyPlaying = false;
  lastWifiConnected = false;
  lastWifiStatusText = "";
  wifiConnected = false;

  updateGui();

  Serial.println("TFT display and graph initialized (Croissant)");
}

void initializeWiFi() {
  WiFi.mode(WIFI_STA);

  wm.setConfigPortalBlocking(false);
  wm.setConfigPortalTimeout(300);
  wm.setConnectTimeout(5);
  wm.setSaveConnectTimeout(10);

  bool wifiStarted = wm.autoConnect(WIFI_AP_NAME);

  if (wifiStarted) {
    Serial.println("WiFi connected immediately");
    wifiConnected = true;
    udp.begin(OSC_PORT);
    Serial.printf("OSC listening on UDP port %d, path: %s\n", OSC_PORT, OSC_PATH);
  } else {
    Serial.println("WiFi connection attempt started (non-blocking)");
    wifiConnected = false;
  }
}

void initializeTactileOutputs() {
#if ENABLE_TACTILE_OUTPUT
  if (!tactile_output_begin()) {
    Serial.println("WARNING: tactile output init failed");
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

  Serial.printf("\nCroissant station %d (one LilyGO per station)\n", STATION_ID);
  Serial.println("Serial: v1[,v2,...],timestamp");
  Serial.printf("OSC: %s  typetag ,f...fs\n", OSC_PATH);
#if ENABLE_PWM_OUTPUT
  Serial.println("Motors: Pin_A/B -> PWM GPIO 25, 26");
#endif
#if ENABLE_DY_HV20T
  Serial.println("DY-HV20T: GPIO 17 TX, Play=21 Stop=22; Serial DY,PLAY | DY,STOP (same as dust_devil)");
#if DY_GATE_TACTILE_OUTPUT
  Serial.println("Output gate: Play = PWM to amps; Stop = mute PWM");
#endif
#endif
  Serial.println("==========================================");

#if ENABLE_DY_HV20T
  // Mute the module before TFT/WiFi so it cannot keep playing through boot.
  dy_hv20t_begin();
#endif

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

  initializeTactileOutputs();
}

void loop() {
  processSerialMessages();
#if ENABLE_DY_HV20T
  dy_hv20t_update();
#endif
  updateTactileOutputs();
  wm.process();
  updateWiFiStatus();
  if (wifiConnected) {
    processOSCMessages();
  }
  updateGui();
  delay(1);
}

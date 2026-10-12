#include "input.h"
#include "helpers.h"
#include "settings.h"

#include <WiFi.h>

static const int SERIAL_BUFFER_SIZE = 384;
static const int OSC_BUFFER_SIZE = 512;

static String s_serialBuffer;
static unsigned long s_lastSerialCharTime = 0;
static bool s_serialReceiving = false;

static uint8_t s_oscBuffer[OSC_BUFFER_SIZE];
static unsigned long s_lastOscTime = 0;
static bool s_oscReceiving = false;

static PinFrameCallback s_onFrame = nullptr;
static CarrierHzCallback s_onCarrier = nullptr;

void input_begin() {
  s_serialBuffer.reserve(SERIAL_BUFFER_SIZE);
  s_serialReceiving = false;
  s_oscReceiving = false;
}

void input_setCallbacks(PinFrameCallback onFrame, CarrierHzCallback onCarrier) {
  s_onFrame = onFrame;
  s_onCarrier = onCarrier;
}

bool input_serialReceiving() { return s_serialReceiving; }
bool input_oscReceiving() { return s_oscReceiving; }
bool input_streamActive() { return s_serialReceiving || s_oscReceiving; }

static bool processControlMessage(const String& message) {
  int hz = 0;
  if (!parsePrefixedIntCommand(message, "FREQ", &hz) || s_onCarrier == nullptr) {
    return false;
  }
  s_onCarrier((float)hz);
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
  int n = parseCsvFloats(valuesPart, values, MAX_PINS);
  if (n == 0 || s_onFrame == nullptr) {
    return;
  }

  s_serialReceiving = true;
  s_lastSerialCharTime = millis();
  s_onFrame(values, n);
}

void input_processSerial() {
  if (Serial.available() > 0) {
    s_lastSerialCharTime = millis();
    s_serialReceiving = true;
    appendSerialBytes(s_serialBuffer, SERIAL_BUFFER_SIZE);

    String latestMessage;
    if (takeLatestSerialLine(s_serialBuffer, &latestMessage)) {
      processSerialMessage(latestMessage);
    }
  }

  if (s_serialReceiving && streamTimedOut(s_lastSerialCharTime)) {
    s_serialReceiving = false;
  }
  if (s_serialBuffer.length() > 0 && (millis() - s_lastSerialCharTime) > SERIAL_TIMEOUT_MS) {
    s_serialBuffer = "";
  }
}

static int readLatestOscPacket(WiFiUDP& udp) {
  int latestPacketSize = 0;
  int packetCount = 0;

  while (true) {
    int packetSize = udp.parsePacket();
    if (packetSize <= 0) {
      break;
    }
    packetCount++;
    if (packetSize > OSC_BUFFER_SIZE) {
      serialDebugPrintf("OSC packet too large: %d bytes\n", packetSize);
      while (udp.available()) {
        udp.read();
      }
      continue;
    }
    int len = udp.read(s_oscBuffer, OSC_BUFFER_SIZE);
    if (len > 0) {
      latestPacketSize = len;
    }
  }

  if (packetCount > 1 && latestPacketSize > 0) {
    serialDebugPrintf("Discarded %d OSC packets, processed latest\n", packetCount - 1);
  }
  return latestPacketSize;
}

void input_processOsc(WiFiUDP& udp) {
  if (WiFi.status() != WL_CONNECTED) {
    return;
  }

  int latestPacketSize = readLatestOscPacket(udp);
  if (latestPacketSize > 0) {
    s_oscReceiving = true;
    s_lastOscTime = millis();

    float oscVals[MAX_PINS];
    int fcnt = 0;
    if (parseOSCMessageMulti(s_oscBuffer, latestPacketSize, oscVals, MAX_PINS, &fcnt)) {
      if (s_onFrame != nullptr) {
        s_onFrame(oscVals, (fcnt < MAX_PINS) ? fcnt : MAX_PINS);
      }
    } else {
      serialDebugPrintln("Failed to parse OSC message");
    }
  }

  if (s_oscReceiving && streamTimedOut(s_lastOscTime)) {
    s_oscReceiving = false;
  }
}

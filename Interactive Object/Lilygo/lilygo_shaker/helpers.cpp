#include "helpers.h"
#include "settings.h"

#include <WiFi.h>
#include <TFT_eSPI.h>
#include <string.h>
#include <math.h>

// =============================================================================
// Levels / timing
// =============================================================================

float scaleShakeLevel(float level01) {
  if (!(level01 > 0.0f)) {
    return 0.0f;
  }
  if (level01 >= 1.0f) {
    return 1.0f;
  }
  return SHAKE_LEVEL_FLOOR + level01 * (1.0f - SHAKE_LEVEL_FLOOR);
}

bool sanitizeLevel01(float* v) {
  if (v == nullptr || isnan(*v) || isinf(*v) || *v < 0.0f || *v > 1.0f) {
    return false;
  }
  return true;
}

bool streamTimedOut(unsigned long lastActivityMs) {
  return (millis() - lastActivityMs) > STREAM_IDLE_TIMEOUT_MS;
}

// =============================================================================
// Serial / CSV parsing
// =============================================================================

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

bool parsePrefixedIntCommand(const String& message, const char* key, int* outHz) {
  String msg = message;
  msg.trim();
  const size_t keyLen = strlen(key);
  if (msg.length() <= (int)keyLen + 1 || !msg.startsWith(key)) {
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

int parseCsvFloats(const String& csv, float* out, int maxOut) {
  int n = 0;
  int start = 0;
  for (int i = 0; i <= (int)csv.length(); i++) {
    if (i != (int)csv.length() && csv.charAt(i) != ',') {
      continue;
    }
    String token = csv.substring(start, i);
    token.trim();
    if (token.length() > 0 && n < maxOut) {
      float v;
      parseFloatToken(token, &v);
      out[n++] = v;
    }
    start = i + 1;
  }
  return n;
}

void appendSerialBytes(String& buffer, int maxSize) {
  while (Serial.available() > 0) {
    char c = Serial.read();
    if (c == '\n' || c == '\r') {
      buffer += '\n';
    } else if (c >= 32 && c <= 126) {
      buffer += c;
      if ((int)buffer.length() >= maxSize - 1) {
        buffer = "";
      }
    }
  }
}

bool takeLatestSerialLine(String& buffer, String* outMessage) {
  int lastNewline = buffer.lastIndexOf('\n');
  if (lastNewline < 0) {
    return false;
  }

  int messageStart = 0;
  for (int i = lastNewline - 1; i >= 0; i--) {
    if (buffer.charAt(i) == '\n') {
      messageStart = i + 1;
      break;
    }
  }

  *outMessage = buffer.substring(messageStart, lastNewline);
  buffer = (lastNewline < (int)buffer.length() - 1) ? buffer.substring(lastNewline + 1)
                                                    : String("");
  return outMessage->length() > 0;
}

// =============================================================================
// OSC parsing
// =============================================================================

static int alignTo4Bytes(int offset) { return (offset + 3) & ~3; }

static float readOscFloatBe(const uint8_t* p) {
  union {
    uint8_t bytes[4];
    float val;
  } u;
  u.bytes[3] = p[0];
  u.bytes[2] = p[1];
  u.bytes[1] = p[2];
  u.bytes[0] = p[3];
  return u.val;
}

bool parseOSCMessageMulti(const uint8_t* buffer, int packetSize, float* outValues,
                          int maxValues, int* outFloatCount) {
  *outFloatCount = 0;
  if (packetSize < 8 || buffer == nullptr) {
    return false;
  }

  int pathLen = 0;
  while (pathLen < packetSize && buffer[pathLen] != 0) {
    pathLen++;
  }
  if (pathLen != (int)strlen(OSC_PATH) || memcmp(buffer, OSC_PATH, pathLen) != 0) {
    return false;
  }

  int offset = alignTo4Bytes(pathLen + 1);
  if (offset >= packetSize || buffer[offset] != ',') {
    return false;
  }

  int p = offset + 1;
  int fCount = 0;
  while (p < packetSize && buffer[p] == 'f') {
    fCount++;
    p++;
  }
  if (p >= packetSize || buffer[p] != 's') {
    return false;
  }
  p++;
  while (p < packetSize && buffer[p] != 0) {
    p++;
  }
  if (p >= packetSize) {
    return false;
  }
  offset = alignTo4Bytes(p + 1);

  for (int fi = 0; fi < fCount; fi++) {
    if (offset + 4 > packetSize) {
      return false;
    }
    if (fi < maxValues) {
      outValues[fi] = readOscFloatBe(buffer + offset);
    }
    offset += 4;
  }

  if (offset >= packetSize) {
    return false;
  }
  while (offset < packetSize && buffer[offset] != 0) {
    offset++;
  }
  if (offset >= packetSize) {
    return false;
  }

  *outFloatCount = fCount;
  return true;
}

// =============================================================================
// WiFi status text
// =============================================================================

void wifiStatusLabel(String* text, int* color) {
  if (WiFi.status() == WL_CONNECTED) {
    *text = WiFi.localIP().toString();
    *color = TFT_GREEN;
  } else if (WiFi.getMode() == WIFI_AP || WiFi.getMode() == WIFI_AP_STA) {
    *text = "Config: " + WiFi.softAPIP().toString();
    *color = TFT_YELLOW;
  } else {
    String ssid = WiFi.SSID();
    *text = (ssid.length() > 0) ? ("Connecting: " + ssid) : String("Connecting...");
    *color = TFT_CYAN;
  }
  if (text->length() > 14) {
    *text = text->substring(0, 11) + "...";
  }
}

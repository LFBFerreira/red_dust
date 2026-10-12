#pragma once

#include <Arduino.h>

// --- Levels / timing ---

// Exact 0 stays off; (0,1] -> [SHAKE_LEVEL_FLOOR, 1].
float scaleShakeLevel(float level01);

// True if v is finite and in [0, 1].
bool sanitizeLevel01(float* v);

// True when lastActivityMs is older than STREAM_IDLE_TIMEOUT_MS.
bool streamTimedOut(unsigned long lastActivityMs);

// --- Serial / CSV parsing ---

bool parseFloatToken(const String& token, float* out);

// "FREQ,32" / "FREQ=32" -> hz; false if not this command or invalid.
bool parsePrefixedIntCommand(const String& message, const char* key, int* outHz);

// Parse comma-separated floats into out[]; returns count (0..maxOut).
int parseCsvFloats(const String& csv, float* out, int maxOut);

// Keep printable ASCII; normalize CR/LF to '\n'. Clear buffer if it overflows.
void appendSerialBytes(String& buffer, int maxSize);

// Latest complete line into outMessage; keeps trailing partial in buffer.
bool takeLatestSerialLine(String& buffer, String* outMessage);

// --- OSC parsing ---

// Typetag ,f...fs (>=0 floats, then timestamp string). Path must match OSC_PATH.
bool parseOSCMessageMulti(const uint8_t* buffer, int packetSize, float* outValues,
                          int maxValues, int* outFloatCount);

// --- WiFi status text ---

// Short label + TFT color for the status bar (truncates long strings).
void wifiStatusLabel(String* text, int* color);

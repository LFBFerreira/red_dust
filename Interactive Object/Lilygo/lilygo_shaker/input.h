#pragma once

#include <Arduino.h>
#include <WiFiUdp.h>

// Serial + OSC ingest (common to both boards).

typedef void (*PinFrameCallback)(const float* values, int count);
typedef void (*CarrierHzCallback)(float hz);

void input_begin();
void input_setCallbacks(PinFrameCallback onFrame, CarrierHzCallback onCarrier);

bool input_serialReceiving();
bool input_oscReceiving();
bool input_streamActive();

void input_processSerial();
void input_processOsc(WiFiUDP& udp);

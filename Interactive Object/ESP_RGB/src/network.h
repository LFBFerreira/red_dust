#ifndef NETWORK_H
#define NETWORK_H

#include <Arduino.h>
#include <WiFi.h>
#include <WiFiUdp.h>

// Network state getters
bool isWiFiConnected();
bool isInAPMode();
bool isWiFiSetupComplete();

// Network initialization
void setupNetwork();

// Network processing (call in loop)
void processNetwork();

// WiFi setup handling (call when setup not complete)
void handleWiFiSetup();

// WiFi status handling (call when setup complete)
void handleWiFiStatus();

// Get UDP instance for OSC
WiFiUDP& getUDP();

// Get local port
unsigned int getLocalPort();

#endif // NETWORK_H

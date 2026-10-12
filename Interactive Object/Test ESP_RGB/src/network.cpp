#include "network.h"

// Network configuration
const unsigned int localPort = 8000;
const char* apName = "RedDust_Object";
const char* wifiSSID = "IBelieveICanWifi";
const char* wifiPassword = "Sayplease2times";

// Network state
static bool wifiConnected = false;
static bool inAPMode = false;
static bool wifiSetupComplete = false;
static WiFiUDP Udp;
static unsigned long lastReconnectAttempt = 0;
static const unsigned long RECONNECT_INTERVAL = 10000;  // Try to reconnect every 10 seconds

// Called when WiFi successfully connects
void onWiFiConnected() {
  wifiConnected = true;
  wifiSetupComplete = true;
  inAPMode = false;
  Serial.println("WiFi connected!");
  Serial.print("IP address: ");
  Serial.println(WiFi.localIP());
  Serial.print("Listening for OSC messages on port ");
  Serial.println(localPort);
  
  // Start UDP server
  Udp.begin(localPort);
  
  Serial.println("Ready to receive OSC messages");
}

// State getters
bool isWiFiConnected() {
  return wifiConnected;
}

bool isInAPMode() {
  return inAPMode;
}

bool isWiFiSetupComplete() {
  return wifiSetupComplete;
}

WiFiUDP& getUDP() {
  return Udp;
}

unsigned int getLocalPort() {
  return localPort;
}

// Handle WiFi setup phase (when not yet connected)
void handleWiFiSetup() {
  // Check if we're in AP mode (portal is running)
  if (WiFi.getMode() == WIFI_AP || WiFi.getMode() == WIFI_AP_STA) {
    if (!inAPMode) {
      // Just entered AP mode
      inAPMode = true;
      Serial.println("AP mode detected - Config portal should be accessible");
      Serial.print("AP IP: ");
      Serial.println(WiFi.softAPIP());
    }
  }
  
  // Check if WiFi is now connected
  if (WiFi.status() == WL_CONNECTED) {
    onWiFiConnected();
  }
}

// Handle WiFi status LED blinking (no longer used, kept for compatibility)
void handleWiFiStatusLED() {
  // LED control removed - now handled centrally in main.cpp
}

// Handle WiFi reconnection
void handleWiFiReconnection() {
  if (!wifiConnected) {
    // Just reconnected
    wifiConnected = true;
    Serial.println("WiFi reconnected!");
    Serial.print("IP address: ");
    Serial.println(WiFi.localIP());
    Udp.begin(localPort);
  }
}

// Handle WiFi disconnection
void handleWiFiDisconnection() {
  if (wifiConnected) {
    wifiConnected = false;
    Serial.println("WiFi disconnected! Attempting to reconnect...");
  }
}

// Handle WiFi status (reconnection/disconnection)
void handleWiFiStatus() {
  if (WiFi.status() == WL_CONNECTED) {
    // Handle reconnection if needed
    handleWiFiReconnection();
  } else {
    // Handle disconnection
    handleWiFiDisconnection();
  }
  
  // Update WiFi status LED blinking
  handleWiFiStatusLED();
}

// Network initialization
void setupNetwork() {
  Serial.println("Connecting to WiFi...");
  Serial.print("SSID: ");
  Serial.println(wifiSSID);
  
  // Initialize WiFi in station mode
  WiFi.mode(WIFI_STA);
  WiFi.begin(wifiSSID, wifiPassword);
  
  inAPMode = false;
  wifiSetupComplete = false;
  wifiConnected = false;
  lastReconnectAttempt = 0;  // Will trigger immediate connection attempt
  
  // Wait for connection (non-blocking, will check in loop)
  Serial.println("WiFi connection initiated...");
}

// Network processing (call in loop)
void processNetwork() {
  // Check WiFi connection status
  if (WiFi.status() == WL_CONNECTED) {
    if (!wifiConnected) {
      // Just connected
      onWiFiConnected();
    }
    // Reset reconnect timer when connected
    lastReconnectAttempt = 0;
  } else {
    // Not connected - attempt reconnection
    unsigned long currentTime = millis();
    
    // Check if we should attempt reconnection
    bool shouldReconnect = false;
    
    if (wifiConnected) {
      // Was connected but now disconnected - reconnect immediately
      wifiConnected = false;
      shouldReconnect = true;
      Serial.println("WiFi disconnected! Attempting to reconnect...");
    } else if (lastReconnectAttempt == 0 || 
               (currentTime - lastReconnectAttempt) >= RECONNECT_INTERVAL) {
      // Either initial connection attempt or time for periodic retry
      shouldReconnect = true;
      if (lastReconnectAttempt > 0) {
        Serial.println("WiFi not connected. Retrying connection...");
      }
    }
    
    if (shouldReconnect) {
      // Attempt to reconnect
      WiFi.disconnect();
      delay(100);  // Brief delay to ensure disconnect completes
      WiFi.mode(WIFI_STA);
      WiFi.begin(wifiSSID, wifiPassword);
      lastReconnectAttempt = currentTime;
    }
  }
}

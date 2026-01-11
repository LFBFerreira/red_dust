#include "network.h"
#include <FastLED.h>

// Forward declarations for LED control callbacks
extern CRGB leds[];
extern unsigned long lastBlinkTime;
extern bool blinkState;
extern CRGB blinkColor;
extern void updateBlink();

// Network configuration
const unsigned int localPort = 8000;
const char* apName = "RedDust_Object";

// WiFiManager instance
WiFiManager wm;

// Network state
static bool wifiConnected = false;
static bool inAPMode = false;
static bool wifiSetupComplete = false;
static WiFiUDP Udp;

// WiFiManager callback for when AP mode starts
void configModeCallback(WiFiManager *myWiFiManager) {
  Serial.println("Entered AP mode");
  Serial.print("AP SSID: ");
  Serial.println(myWiFiManager->getConfigPortalSSID());
  Serial.print("AP IP: ");
  Serial.println(WiFi.softAPIP());
  inAPMode = true;
  blinkColor = CRGB::Blue;  // Blue blinking for AP mode
  lastBlinkTime = millis();  // Reset blink timer
  blinkState = false;  // Start with LED off
  // Show initial blue blink
  leds[0] = CRGB::Black;
  FastLED.show();
}

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
  
  // Stop blinking and show connection success with green flash
  blinkColor = CRGB::Black;
  leds[0] = CRGB::Green;
  FastLED.show();
  delay(200);
  leds[0] = CRGB::Black;
  FastLED.show();
  
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
      blinkColor = CRGB::Blue;  // Blue blinking for AP mode
      lastBlinkTime = millis();
      blinkState = false;
      Serial.println("AP mode detected - Config portal should be accessible");
      Serial.print("AP IP: ");
      Serial.println(WiFi.softAPIP());
    }
    // Blue blinking for AP mode
    updateBlink();
  } else {
    // Yellow blinking while connecting
    updateBlink();
  }
  
  // Check if WiFi is now connected
  if (WiFi.status() == WL_CONNECTED) {
    onWiFiConnected();
  }
}

// Handle WiFi status LED blinking
void handleWiFiStatusLED() {
  // Update blinking if in AP mode (blue) or disconnected/reconnecting (yellow)
  if (inAPMode) {
    // Blue blinking for AP mode
    updateBlink();
  } else if (WiFi.status() != WL_CONNECTED) {
    // Yellow blinking while disconnected/reconnecting
    if (blinkColor != CRGB::Yellow) {
      blinkColor = CRGB::Yellow;
      lastBlinkTime = 0;  // Reset timer
    }
    updateBlink();
  } else {
    // WiFi connected - stop blinking if needed
    if (inAPMode || blinkColor != CRGB::Black) {
      inAPMode = false;
      blinkColor = CRGB::Black;
      leds[0] = CRGB::Black;
      FastLED.show();
    }
  }
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
    
    // Show reconnection with green flash
    leds[0] = CRGB::Green;
    FastLED.show();
    delay(200);
    leds[0] = CRGB::Black;
    FastLED.show();
  }
}

// Handle WiFi disconnection
void handleWiFiDisconnection() {
  if (wifiConnected) {
    wifiConnected = false;
    Serial.println("WiFi disconnected! Attempting to reconnect...");
    
    // Show disconnection with red flash, then yellow blinking
    leds[0] = CRGB::Red;
    FastLED.show();
    delay(200);
    leds[0] = CRGB::Black;
    FastLED.show();
    
    // Start yellow blinking for reconnection attempt
    blinkColor = CRGB::Yellow;
    lastBlinkTime = 0;
  }
  
  // Show yellow blinking while disconnected (reconnecting)
  if (!inAPMode) {
    blinkColor = CRGB::Yellow;
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
  // WiFiManager - automatically connects using saved credentials
  // If connection fails, it starts an access point for configuration
  // Uncomment the next line to reset saved WiFi credentials (for testing)
  // wm.resetSettings();
  
  // Set callback for when AP mode starts
  wm.setAPCallback(configModeCallback);
  
  // Configure WiFiManager for non-blocking operation
  wm.setConfigPortalBlocking(false);
  wm.setConfigPortalTimeout(0);  // 0 = no timeout, portal stays open until configured
  wm.setAPClientCheck(true);  // Avoid timeout if client connected to softAP
  
  // Show yellow blinking while attempting to connect to saved WiFi
  Serial.println("Connecting to WiFi...");
  blinkColor = CRGB::Yellow;  // Yellow for connecting
  lastBlinkTime = millis();
  inAPMode = false;
  wifiSetupComplete = false;
  
  // Try to connect with saved credentials first
  // In non-blocking mode, autoConnect returns immediately
  bool connected = wm.autoConnect(apName);
  
  if (connected) {
    // WiFi connected immediately
    onWiFiConnected();
  } else {
    // Connection failed - explicitly start config portal
    // This ensures the web server is properly initialized
    Serial.println("Starting config portal explicitly...");
    wm.startConfigPortal(apName);
    
    // Process WiFiManager to initialize the portal
    for (int i = 0; i < 10; i++) {
      wm.process();
      delay(100);
    }
    
    Serial.println("Config portal ready!");
    Serial.print("AP IP: ");
    Serial.println(WiFi.softAPIP());
    Serial.println("Connect to 'RedDust_Object' network and open http://192.168.4.1");
    Serial.println("Waiting for configuration...");
    // Connection will be handled in loop()
  }
}

// Network processing (call in loop)
void processNetwork() {
  // Process WiFiManager (required for non-blocking mode)
  wm.process();
}

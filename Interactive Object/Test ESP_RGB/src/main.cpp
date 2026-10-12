#include <Arduino.h>
#include <WiFiUdp.h>
#include <OSCMessage.h>
#include <FastLED.h>
#include "network.h"

// Pin definitions for ESP32-S3-DevKitC-1
// RGB LED pin varies by board revision:
//   v1.1: GPIO 38
// Try changing this if the LED doesn't work
#define RGB_LED_PIN 38      // Change to 48 if you have v1.0 board

// FastLED configuration
#define NUM_LEDS 1
#define LED_TYPE WS2812B
#define COLOR_ORDER GRB

// OSC configuration
const char* oscAddress = "/red_dust/object_1";

// Serial communication configuration
String serialBuffer = "";
const int SERIAL_BUFFER_SIZE = 128;
const unsigned long SERIAL_TIMEOUT_MS = 1000;  // Message timeout
unsigned long lastSerialCharTime = 0;
bool serialActive = false;  // Track if Serial is actively receiving data
bool serialConnected = false;  // Track if Serial has ever received data (connection established)
bool serialReceivingData = false;  // Track if currently receiving data
const unsigned long SERIAL_INACTIVE_TIMEOUT = 2000;  // Consider Serial inactive after 2s of no data
const unsigned long SERIAL_RECEIVING_TIMEOUT = 100;  // Consider "receiving" if data within last 100ms
CRGB serialColor = CRGB::Black;  // Current color from Serial data

CRGB leds[NUM_LEDS];
CRGB currentColor = CRGB::Black;  // Current color from Serial/OSC data
bool hasColorData = false;  // Whether we have valid color data to display

// Function to map normalized value (0..1) to color between red and blue
CRGB mapValueToColor(float value) {
  // Constrain value to 0..1 range
  value = constrain(value, 0.0, 1.0);
  
  // Linear interpolation: red at 0.0, blue at 1.0
  // Red component decreases as value increases
  uint8_t red = (1.0 - value) * 255;
  // Blue component increases as value increases
  uint8_t blue = value * 255;
  // Green stays at 0 for pure red-blue gradient
  
  return CRGB(red, 0, blue);
}

// OSC message handler
void handleOSCMessage(OSCMessage &msg) {
  if (msg.isFloat(0)) {
    float normalizedValue = msg.getFloat(0);
    
    // Map value to color
    CRGB color = mapValueToColor(normalizedValue);
    currentColor = color;
    hasColorData = true;
    
    Serial.printf("Received OSC: value=%.3f, R=%d, G=0, B=%d\n", 
                  normalizedValue, color.red, color.blue);
  } else {
    Serial.println("Error: OSC message does not contain a float value");
  }
}

// Process incoming OSC messages
void processOSCMessages() {
  WiFiUDP& Udp = getUDP();
  int packetSize = Udp.parsePacket();
  if (packetSize > 0) {
    // Read the packet into a buffer
    OSCMessage msg;
    while (packetSize--) {
      msg.fill(Udp.read());
    }
    
    // Check if message is valid and dispatch to handler
    if (!msg.hasError()) {
      msg.dispatch(oscAddress, handleOSCMessage);
    } else {
      Serial.println("Error: Invalid OSC message format");
    }
  }
}

// Handle Serial value (normalized 0..1)
void handleSerialValue(float value, String timestamp) {
  // Validate value is a valid number (not NaN or infinity)
  if (isnan(value) || isinf(value)) {
    Serial.println("Error: Invalid value (NaN or infinity), ignoring");
    return;
  }
  
  // Clamp value to 0..1 range
  value = constrain(value, 0.0, 1.0);
  
  // Map value to color (Red to Blue)
  CRGB color = mapValueToColor(value);
  currentColor = color;
  hasColorData = true;
  serialColor = color;  // Store the color for reference
  serialReceivingData = true;  // Mark as currently receiving
  lastSerialCharTime = millis();  // Update timestamp
  
  Serial.printf("Received Serial: value=%.6f, R=%d, G=0, B=%d\n", 
                value, color.red, color.blue);
}

// Process Serial message
void processSerialMessage(String message) {
  int commaIndex = message.indexOf(',');
  
  if (commaIndex <= 0 || commaIndex >= message.length() - 1) {
    // Invalid message format
    return;
  }
  
  String valueStr = message.substring(0, commaIndex);
  String timestamp = message.substring(commaIndex + 1);
  
  // Trim whitespace from value string
  valueStr.trim();
  
  // Check if value string is empty
  if (valueStr.length() == 0) {
    return;
  }
  
  // Convert to float
  float value = valueStr.toFloat();
  
  // Check if conversion was successful
  // (toFloat() returns 0.0 on error, so validate the string)
  // Also check if the value is reasonable (within -1000 to 1000 range to catch parsing errors)
  if (valueStr.length() > 0 && 
      (valueStr.indexOf('.') >= 0 || valueStr.toInt() != 0 || valueStr == "0" || valueStr == "0.0") &&
      value >= -1000.0 && value <= 1000.0) {
    // Value will be clamped to 0..1 in handleSerialValue
    handleSerialValue(value, timestamp);
  } else {
    Serial.printf("Error: Invalid serial value format: '%s'\n", valueStr.c_str());
  }
}

// Process incoming Serial messages
void processSerialMessages() {
  // Read all available serial data first
  if (Serial.available() > 0) {
    lastSerialCharTime = millis();
    serialActive = true;  // Mark Serial as active
    serialConnected = true;  // Mark as connected (has received data)
    serialReceivingData = true;  // Currently receiving data
    
    // Read all available characters, accumulating into serialBuffer
    while (Serial.available() > 0) {
      char c = Serial.read();
      
      if (c == '\n' || c == '\r') {
        // End of message - add newline marker to buffer
        serialBuffer += '\n';
      } else if (c >= 32 && c <= 126) {  // Printable ASCII only
        serialBuffer += c;
        
        // Buffer overflow protection
        if (serialBuffer.length() >= SERIAL_BUFFER_SIZE - 1) {
          serialBuffer = "";
        }
      }
    }
    
    // Find and process only the latest complete message
    // Look for the last newline in the buffer
    int lastNewline = serialBuffer.lastIndexOf('\n');
    
    if (lastNewline >= 0) {
      // We have at least one complete message
      // Find the start of the last message (previous newline or start of buffer)
      int messageStart = 0;
      for (int i = lastNewline - 1; i >= 0; i--) {
        if (serialBuffer.charAt(i) == '\n') {
          messageStart = i + 1;
          break;
        }
      }
      
      // Extract the latest complete message (between messageStart and lastNewline)
      String latestMessage = serialBuffer.substring(messageStart, lastNewline);
      
      if (latestMessage.length() > 0) {
        processSerialMessage(latestMessage);
      }
      
      // Clear buffer after processing latest message
      // If there's any data after the last newline, keep it (incomplete message)
      if (lastNewline < serialBuffer.length() - 1) {
        serialBuffer = serialBuffer.substring(lastNewline + 1);
      } else {
        serialBuffer = "";
      }
    }
    // If no newline found, keep the buffer for next iteration (incomplete message)
  }
  
  // Check if we're still "receiving" (data within last 100ms)
  if (serialReceivingData && (millis() - lastSerialCharTime) > SERIAL_RECEIVING_TIMEOUT) {
    serialReceivingData = false;
  }
  
  // Timeout: clear buffer if no data received for a while
  if (serialBuffer.length() > 0 && 
      (millis() - lastSerialCharTime) > SERIAL_TIMEOUT_MS) {
    serialBuffer = "";
  }
  
  // Check if Serial should be considered inactive
  if (serialActive && (millis() - lastSerialCharTime) > SERIAL_INACTIVE_TIMEOUT) {
    serialActive = false;
  }
}

// Check if Serial is actively receiving data
bool isSerialActive() {
  return serialActive;
}

// Check if Serial is connected (has received data)
bool isSerialConnected() {
  return serialConnected;
}

// Update LED based on connection status and received data
// Rules:
// - If neither Serial nor WiFi connected: RED
// - If one or both connected: show color from received data (if any), otherwise black
void updateLED() {
  bool serialIsConnected = isSerialConnected();
  bool wifiIsConnected = isWiFiConnected();
  
  if (!serialIsConnected && !wifiIsConnected) {
    // Neither connected - show red
    leds[0] = CRGB::Red;
  } else if (hasColorData) {
    // One or both connected and we have color data - show the color
    leds[0] = currentColor;
  } else {
    // One or both connected but no data yet - show black
    leds[0] = CRGB::Black;
  }
  
  FastLED.show();
}

void setup() {
  // Initialize serial communication (9600 baud for Red Dust Control Center)
  Serial.begin(115200);
  delay(1000);
  Serial.println("\nESP32-S3-DevKitC-1 RGB LED Controller");
  Serial.println("Supports: Serial (9600) and OSC");
  Serial.println("==========================================");
  
  // Reserve buffer space
  serialBuffer.reserve(SERIAL_BUFFER_SIZE);
  
  // Initialize Serial LED state
  serialConnected = false;
  serialReceivingData = false;
  currentColor = CRGB::Black;
  hasColorData = false;
  
  // Initialize RGB LED (FastLED)
  FastLED.addLeds<LED_TYPE, RGB_LED_PIN, COLOR_ORDER>(leds, NUM_LEDS);
  FastLED.setBrightness(100);  // Set brightness (0-255)
  
  // Initial LED state will be set by updateLED() in loop
  
  // Setup network
  setupNetwork();
}

void loop() {
  // ALWAYS process network - this handles connection and reconnection attempts
  // regardless of Serial status
  processNetwork();
  
  // Process Serial messages (has precedence over OSC)
  processSerialMessages();
  
  // Handle WiFi setup if not complete
  if (!isWiFiSetupComplete()) {
    handleWiFiSetup();
    delay(1);  // Small delay to prevent watchdog issues
  } else {
    // Handle WiFi status (for reconnection/disconnection logic, but LED is controlled by Serial)
    handleWiFiStatus();
    
    // Only process OSC if Serial is not active
    if (!isSerialActive() && WiFi.status() == WL_CONNECTED) {
      // Process incoming OSC messages
      processOSCMessages();
    }
  }
  
  // Update LED based on connection status and received data
  updateLED();
  
  // Small delay to prevent watchdog issues
  delay(1);
}
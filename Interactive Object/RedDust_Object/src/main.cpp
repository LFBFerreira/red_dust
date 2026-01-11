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
unsigned long lastBlinkTime = 0;
bool blinkState = false;
CRGB blinkColor = CRGB::Black;
const unsigned long BLINK_INTERVAL = 1000;  // 1 second for slow blinking

// Separate blink timer for Serial LED status
unsigned long lastSerialBlinkTime = 0;
bool serialBlinkState = false;

// Function to handle LED blinking (non-blocking)
void updateBlink() {
  unsigned long currentTime = millis();
  if (currentTime - lastBlinkTime >= BLINK_INTERVAL) {
    blinkState = !blinkState;
    lastBlinkTime = currentTime;
    leds[0] = blinkState ? blinkColor : CRGB::Black;
    FastLED.show();
  }
}

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
    leds[0] = color;
    FastLED.show();
    
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
  // Clamp value to 0..1 range
  value = constrain(value, 0.0, 1.0);
  
  // Map value to color (Red to Blue)
  CRGB color = mapValueToColor(value);
  serialColor = color;  // Store the color
  serialReceivingData = true;  // Mark as currently receiving
  lastSerialCharTime = millis();  // Update timestamp
  
  // Display the color immediately when receiving data
  leds[0] = color;
  FastLED.show();
  
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
  
  // Convert to float
  float value = valueStr.toFloat();
  
  // Check if conversion was successful
  // (toFloat() returns 0.0 on error, so validate the string)
  if (valueStr.length() > 0 && 
      (valueStr.indexOf('.') >= 0 || valueStr.toInt() != 0 || valueStr == "0")) {
    handleSerialValue(value, timestamp);
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

// Update LED based on Serial connection state
// This function should be called frequently and always takes precedence over WiFi LED
void updateSerialLED() {
  unsigned long currentTime = millis();
  
  if (serialReceivingData) {
    // Currently receiving data - show the color from the data
    leds[0] = serialColor;
    FastLED.show();
  } else if (serialConnected) {
    // Connected but not currently receiving - blinking blue
    if (currentTime - lastSerialBlinkTime >= BLINK_INTERVAL) {
      serialBlinkState = !serialBlinkState;
      lastSerialBlinkTime = currentTime;
      leds[0] = serialBlinkState ? CRGB::Blue : CRGB::Black;
      FastLED.show();
    }
  } else {
    // Available but nothing connected - solid blue
    // Always set this immediately (no conditional) to override any WiFi LED changes
    leds[0] = CRGB::Blue;
    FastLED.show();
  }
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
  serialBlinkState = false;
  lastSerialBlinkTime = 0;
  
  // Initialize RGB LED (FastLED)
  FastLED.addLeds<LED_TYPE, RGB_LED_PIN, COLOR_ORDER>(leds, NUM_LEDS);
  FastLED.setBrightness(100);  // Set brightness (0-255)
  leds[0] = CRGB::Blue;        // Start with solid blue (Serial available, nothing connected)
  FastLED.show();
  
  // Setup network (WiFiManager)
  setupNetwork();
}

void loop() {
  // Process network (WiFiManager)
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
  
  // ALWAYS update Serial LED at the end of every loop iteration
  // This ensures Serial LED status always takes precedence over any WiFi LED updates
  // Serial LED is the only thing that should control the RGB LED
  updateSerialLED();
  
  // Small delay to prevent watchdog issues
  delay(1);
}
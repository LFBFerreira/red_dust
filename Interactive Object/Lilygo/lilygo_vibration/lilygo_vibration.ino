// Configuration settings
#include "settings.h"

// TFT Display includes
#include <TFT_eSPI.h>
TFT_eSPI tft = TFT_eSPI();

#include <TFT_eWidget.h>               // Widget library

// WiFi Manager includes
// Fix for ESP32 3.x - include FS.h and bring FS into global namespace
#include <FS.h>
using fs::FS;
#include <WiFi.h>
#include <WiFiUdp.h>
#include <WiFiManager.h> // https://github.com/tzapu/WiFiManager
#include <string.h>  // For strlen() and memcmp() in optimized OSC parsing
WiFiManager wm;

GraphWidget gr = GraphWidget(&tft);    // Graph widget gr instance with pointer to tft
TraceWidget tr = TraceWidget(&gr);     // Graph trace tr with pointer to gr

// Graph configuration
const float gxLow  = 0.0;
const float gxHigh = 200.0;            // X-axis: number of data points
const float gyLow  = 0.0;              // Y-axis: minimum value (0)
const float gyHigh = 10.0;             // Y-axis: maximum value (10.0, scaled from 1.0 for better grid resolution)

// Graph state
float graphX = 0.0;                     // Current X position on graph
bool graphInitialized = false;

// Status display state
float latestValue = 0.0;                 // Latest received value for display
bool lastSerialConnected = false;        // Last connection state (for update detection)
bool lastSerialReceiving = false;       // Last Serial receiving state (for update detection)
bool lastOscReceiving = false;          // Last OSC receiving state (for update detection)
float lastDisplayedValue = -1.0;        // Last displayed value (for update detection)

// WiFi state
bool wifiConnected = false;              // Track WiFi connection status
bool lastWifiConnected = false;         // Last WiFi connection state (for update detection)
String lastWifiStatusText = "";         // Last WiFi status text displayed (for update detection)

// Serial communication configuration
String serialBuffer = "";
const int SERIAL_BUFFER_SIZE = 128;
const unsigned long SERIAL_TIMEOUT_MS = 1000;  // Message timeout
unsigned long lastSerialCharTime = 0;
bool serialConnected = false;  // Track if Serial port is open/connected (has received data)
bool serialReceivingData = false;  // Track if Serial is actively receiving data
const unsigned long SERIAL_RECEIVING_TIMEOUT = 500;  // Consider "receiving" if data within last 100ms

// OSC communication configuration
WiFiUDP udp;
const int OSC_BUFFER_SIZE = 256;
uint8_t oscBuffer[OSC_BUFFER_SIZE];
bool oscReceivingData = false;  // Track if OSC is actively receiving data
unsigned long lastOscTime = 0;
const unsigned long OSC_RECEIVING_TIMEOUT = 500;  // Consider "receiving" if data within last 100ms

int currentPWM = 0;  // Current PWM value from Serial data
bool hasPWMData = false;  // Whether we have valid PWM data to output

// Loop iteration counter for debug messages
unsigned long loopCounter = 0;

// Data source enumeration
enum DataSource {
  SOURCE_SERIAL,
  SOURCE_OSC
};

// Helper function to convert DataSource enum to string for logging
const char* sourceToString(DataSource source) {
  switch (source) {
    case SOURCE_SERIAL:
      return "Serial";
    case SOURCE_OSC:
      return "OSC";
    default:
      return "Unknown";
  }
}

// Function to map normalized value (0..1) to PWM value
int mapValueToPWM(float value) {
  // Constrain value to 0..1 range
  value = constrain(value, 0.0, 1.0);
  
  // Map value to PWM range (linear interpolation)
  int pwmValue = (int)(value * (PWM_MAX - PWM_MIN) + PWM_MIN);
  
  // Ensure result is within valid PWM range
  return constrain(pwmValue, PWM_MIN, PWM_MAX);
}

// Handle value from any source (Serial or OSC) - normalized 0..1
void handleValue(float value, String timestamp, DataSource source) {
  // Validate value is a valid number (not NaN or infinity)
  if (isnan(value) || isinf(value)) {
    Serial.printf("Error: Invalid value (NaN or infinity) from %s, ignoring\n", sourceToString(source));
    return;
  }
  
  // Mark the appropriate source as receiving data
  if (source == SOURCE_OSC) {
    oscReceivingData = true;
    lastOscTime = millis();
  }
  // Serial is already handled in handleSerialValue()
  
  // Clamp value to 0..1 range (strictly enforce limits)
  value = constrain(value, 0.0, 1.0);
  
  // Store latest value for display (already constrained)
  latestValue = constrain(value, 0.0, 1.0);
  
  // Map value to PWM
  int pwmValue = mapValueToPWM(value);
  currentPWM = pwmValue;
  hasPWMData = true;
  
  Serial.printf("Received %s: value=%.6f, PWM=%d\n", sourceToString(source), value, pwmValue);
  
  // Add point to graph if initialized
  // Ensure value is constrained to 0..1 before adding to graph
  // Scale value by 10 for graph display (0-1 becomes 0-10) but keep original for PWM
  if (graphInitialized) {
    float graphValue = constrain(value, 0.0, 1.0) * 10.0;  // Scale by 10 for graph
    tr.addPoint(graphX, graphValue);
    graphX += 1.0;
    
    // If the end of the graph x axis is reached, reset and start a new trace
    if (graphX > gxHigh) {
      graphX = 0.0;
      
      // Draw empty graph to clear old one (positioned below status text)
      gr.drawGraph(10, 25);
      // Start new trace
      tr.startTrace(GRAPH_TRACE_COLOR);
    }
  }
}

// Handle Serial value (normalized 0..1)
void handleSerialValue(float value, String timestamp) {
  serialReceivingData = true;  // Mark as currently receiving
  lastSerialCharTime = millis();  // Update timestamp
  handleValue(value, timestamp, SOURCE_SERIAL);
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
}

// Check if Serial is connected (has received data)
bool isSerialConnected() {
  return serialConnected;
}

// Check if Serial is actively receiving data
bool isSerialReceiving() {
  return serialReceivingData;
}

// Helper function to align to 4-byte boundary (OSC requirement)
int alignTo4Bytes(int offset) {
  return (offset + 3) & ~3;
}

// Parse OSC message and extract float only (optimized - no String operations)
bool parseOSCMessageFast(uint8_t* buffer, int packetSize, float* outValue) {
  if (packetSize < 8) return false;  // Minimum size for path
  
  int offset = 0;
  
  // Check path using direct byte comparison (faster than String concatenation)
  const char* oscPath = OSC_PATH;
  int oscPathLen = strlen(oscPath);
  int pathLen = 0;
  while (offset + pathLen < packetSize && buffer[offset + pathLen] != 0) {
    pathLen++;
  }
  
  // Direct byte comparison - much faster than String operations
  if (pathLen != oscPathLen || memcmp(buffer + offset, oscPath, pathLen) != 0) {
    return false;  // Not our message
  }
  
  offset = alignTo4Bytes(offset + pathLen + 1);  // Skip null terminator and align
  
  if (offset >= packetSize) return false;
  
  // Read type tag (starts with ',', null-terminated, padded to 4-byte boundary)
  if (buffer[offset] != ',') return false;  // Must start with comma
  offset++;
  
  // Check type tag is "fs" using direct byte comparison (faster than String)
  if (offset + 2 > packetSize || buffer[offset] != 'f' || buffer[offset + 1] != 's' || buffer[offset + 2] != 0) {
    return false;  // Wrong type tag
  }
  offset = alignTo4Bytes(offset + 3);  // Skip "fs" + null terminator and align
  
  // Read float (4 bytes, big-endian)
  if (offset + 4 > packetSize) return false;
  
  union {
    uint8_t bytes[4];
    float value;
  } floatUnion;
  
  // Convert from big-endian to little-endian
  floatUnion.bytes[3] = buffer[offset];
  floatUnion.bytes[2] = buffer[offset + 1];
  floatUnion.bytes[1] = buffer[offset + 2];
  floatUnion.bytes[0] = buffer[offset + 3];
  
  *outValue = floatUnion.value;
  
  return true;
}

// Process incoming OSC messages (optimized - only process latest packet)
void processOSCMessages() {
  // Only process if WiFi is connected
  if (WiFi.status() != WL_CONNECTED) {
    return;
  }
  
  // Read all available packets, keeping only the latest one
  // Each packet overwrites the previous one in the buffer
  int latestPacketSize = 0;
  int packetCount = 0;
  
  // Process all queued packets, but only keep the latest
  while (true) {
    int packetSize = udp.parsePacket();
    if (packetSize <= 0) break;  // No more packets
    
    packetCount++;
    
    // Limit packet size to our buffer
    if (packetSize > OSC_BUFFER_SIZE) {
      Serial.printf("OSC packet too large: %d bytes\n", packetSize);
      udp.flush();  // Discard oversized packet
      continue;
    }
    
    // Read packet into buffer (overwrites previous packet)
    int len = udp.read(oscBuffer, OSC_BUFFER_SIZE);
    if (len > 0) {
      latestPacketSize = len;
    }
    // Continue loop to check for more packets (latest will overwrite this one)
  }
  
  // Process only the latest packet if we have one
  if (latestPacketSize > 0) {
    oscReceivingData = true;
    lastOscTime = millis();
    
    // Parse OSC message (fast version, no timestamp)
    float value;
    if (parseOSCMessageFast(oscBuffer, latestPacketSize, &value)) {
      // Valid OSC message - process it (empty timestamp since we don't use it)
      handleValue(value, "", SOURCE_OSC);
    } else {
      Serial.println("Failed to parse OSC message");
    }
    
    // Log if we discarded packets (for debugging - can be removed for production)
    if (packetCount > 1) {
      Serial.printf("Discarded %d OSC packets, processed latest\n", packetCount - 1);
    }
  }
  
  // Check if we're still "receiving" (data within last 100ms)
  if (oscReceivingData && (millis() - lastOscTime) > OSC_RECEIVING_TIMEOUT) {
    oscReceivingData = false;
  }
}

// Update status text display
void updateGui() {
  // Build WiFi status text
  String wifiStatusText = "";
  int wifiStatusColor = TFT_WHITE;
  
  if (WiFi.status() == WL_CONNECTED) {
    // Connected - show IP address
    wifiStatusText = WiFi.localIP().toString();
    wifiStatusColor = TFT_GREEN;
  } else if (WiFi.getMode() == WIFI_AP || WiFi.getMode() == WIFI_AP_STA) {
    // Config portal active - show portal address
    wifiStatusText = "Config: " + WiFi.softAPIP().toString();
    wifiStatusColor = TFT_YELLOW;
  } else {
    // Trying to connect - show SSID if available
    String ssid = WiFi.SSID();
    if (ssid.length() > 0) {
      wifiStatusText = "Connecting: " + ssid;
    } else {
      wifiStatusText = "Connecting...";
    }
    wifiStatusColor = TFT_CYAN;
  }
  
  // Truncate WiFi status text if too long to prevent overlap (max ~14 chars to fit before center at 100px)
  // Font 2 size 1 is ~6px per char, so 14 chars = 84px, leaving room before center text at 100px
  if (wifiStatusText.length() > 14) {
    wifiStatusText = wifiStatusText.substring(0, 11) + "...";
  }
  
  // Check if we need to update the display
  bool needsUpdate = false;
  bool isReceivingData = serialReceivingData || oscReceivingData;  // Check both Serial and OSC
  if (serialConnected != lastSerialConnected || 
      serialReceivingData != lastSerialReceiving ||
      oscReceivingData != lastOscReceiving ||
      abs(latestValue - lastDisplayedValue) > 0.0001 ||
      wifiStatusText != lastWifiStatusText ||
      wifiConnected != lastWifiConnected) {
    needsUpdate = true;
  }
  
  if (!needsUpdate) {
    return;
  }
  
  // Set text properties
  tft.setTextFont(2);  // Use built-in font 2 (small, readable)
  tft.setTextSize(1);
  tft.setTextColor(TFT_WHITE, TFT_BLACK, true);  // White text, black background with fill
  
  // Clear status area (top 20 pixels, full width)
  tft.fillRect(0, 0, 240, 20, TFT_BLACK);
  
  // Left: WiFi Connection status (5px from left)
  tft.setCursor(5, 5);
  tft.setTextColor(wifiStatusColor, TFT_BLACK, true);
  tft.print(wifiStatusText);
  
  // Center: Active status (moved to the right)
  // Shows "Active" if either Serial or OSC is receiving data
  tft.setCursor(120, 5);
  if (isReceivingData) {
    tft.setTextColor(TFT_CYAN, TFT_BLACK, true);
    tft.print("Active");
  } else {
    tft.setTextColor(TFT_YELLOW, TFT_BLACK, true);
    tft.print("Idle");
  }
  
  // Right: Latest value (moved further to the right)
  // Ensure value is constrained to 0..1 before display
  float displayValue = constrain(latestValue, 0.0, 1.0);
  tft.setCursor(190, 5);
  tft.setTextColor(TFT_WHITE, TFT_BLACK, true);
  // tft.print("Val: ");
  tft.print(displayValue, 3);  // 3 decimal places
  
  // Update last displayed states
  lastSerialConnected = serialConnected;
  lastSerialReceiving = serialReceivingData;
  lastOscReceiving = oscReceivingData;
  lastDisplayedValue = latestValue;
  lastWifiStatusText = wifiStatusText;
  lastWifiConnected = wifiConnected;
}

// Update vibration motor PWM based on received data
void updateVibrationMotor() {
  if (hasPWMData) {
    // We have PWM data - output it using LEDC (ESP32 3.x API uses pin number)
    ledcWrite(VIBRATION_MOTOR_PIN, currentPWM);
  } else {
    // No data yet - turn off motor
    ledcWrite(VIBRATION_MOTOR_PIN, 0);
  }
}

// Initialize TFT display and graph
void initializeDisplay() {
  // Initialize TFT display
  tft.init();
  tft.setRotation(3);  // Landscape orientation
  tft.fillScreen(TFT_BLACK);
  
  // Enable backlight (pin 4 for TTGO T-Display)
  pinMode(4, OUTPUT);
  digitalWrite(4, HIGH);
  
  // Graph area sized to fit available space below status bar
  // Display is 240x135, status bar is 20px high, graph starts at y=25
  // Leave margins: 10px left, 15px right, 10px bottom
  // Graph size: 215 pixels wide (10 to 225), 100 pixels high (25 to 125)
  gr.createGraph(220, 100, tft.color565(5, 5, 5));
  
  // X scale units is from 0 to 200 (data points), y scale units is 0 to 10 (scaled from 0-1 for better grid resolution)
  gr.setGraphScale(gxLow, gxHigh, gyLow, gyHigh);
  
  // X grid disabled (spacing larger than range to prevent vertical lines)
  // Y grid starts at 0 with lines every 2 y-scale units (horizontal lines at 0, 2, 4, 6, 8, 10)
  // This corresponds to original values of 0, 0.2, 0.4, 0.6, 0.8, 1.0
  // blue grid
  gr.setGraphGrid(gxLow, 1000, gyLow, 2, GRAPH_GRID_COLOR);
  
  // Draw empty graph, top left corner at pixel coordinate 10,25 on TFT
  // Positioned below status text area (top 20 pixels)
  gr.drawGraph(10, 25);
  
  // Start a trace with red color
  tr.startTrace(GRAPH_TRACE_COLOR);
  
  graphInitialized = true;
  graphX = 0.0;
  
  // Initialize status display state
  latestValue = 0.0;
  lastSerialConnected = false;
  lastSerialReceiving = false;
  lastOscReceiving = false;
  lastDisplayedValue = -1.0;
  lastWifiConnected = false;
  lastWifiStatusText = "";
  wifiConnected = false;
  
  // Draw initial status
  updateGui();
  
  Serial.println("TFT display and graph initialized");
}

// Initialize WiFi Manager and start connection attempt
void initializeWiFi() {
  // Initialize WiFi Manager (non-blocking, after display is ready)
  WiFi.mode(WIFI_STA); // explicitly set mode, esp defaults to STA+AP
  
  // Configure WiFiManager for non-blocking operation
  wm.setConfigPortalBlocking(false);
  wm.setConfigPortalTimeout(300);  // AP portal timeout: 5 minutes (300 seconds)
  
  // Set short connection timeout to minimize blocking in autoConnect()
  // Connection will continue in background via wm.process() in loop()
  wm.setConnectTimeout(5);  // Short timeout (5 seconds) to return quickly
  wm.setSaveConnectTimeout(10);  // Save credentials timeout
  
  // Try to auto-connect (with setConfigPortalBlocking(false), this should return quickly)
  // Connection attempt continues in background via wm.process() in loop()
  // Note: autoConnect() may still block briefly, but graph is already drawn above
  bool wifiStarted = wm.autoConnect("Red_Dust_Object");
  
  if (wifiStarted) {
    // Connected immediately (rare, but possible if credentials are cached)
    Serial.println("WiFi connected immediately");
    wifiConnected = true;
    udp.begin(OSC_PORT);
    Serial.printf("OSC listening on UDP port %d, path: %s\n", OSC_PORT, OSC_PATH);
  } else {
    // Connection attempt started, will complete in loop() via wm.process()
    Serial.println("WiFi connection attempt started (non-blocking)");
    wifiConnected = false;
  }
}

// Initialize vibration motor PWM
void initializeVibrationMotor() {
  // Initialize vibration motor pin with ESP32 LEDC PWM (ESP32 3.x API)
  // Attach pin to LEDC with frequency and resolution (auto-assigns channel)
  ledcAttach(VIBRATION_MOTOR_PIN, PWM_FREQUENCY, PWM_RESOLUTION);
  // Start with motor off
  ledcWrite(VIBRATION_MOTOR_PIN, 0);
  
  Serial.println("Vibration motor initialized on GPIO 25");
}

// Update WiFi connection status and initialize OSC if connected
void updateWiFiStatus() {
  bool currentWifiStatus = (WiFi.status() == WL_CONNECTED);
  if (currentWifiStatus != wifiConnected) {
    wifiConnected = currentWifiStatus;
    if (wifiConnected) {
      Serial.println("WiFi connected");
      // Initialize UDP for OSC
      udp.begin(OSC_PORT);
      Serial.printf("OSC listening on UDP port %d, path: %s\n", OSC_PORT, OSC_PATH);
    } else {
      Serial.println("WiFi disconnected");
    }
  }
}

void setup() {
  // Initialize serial communication
  Serial.begin(SERIAL_BAUDRATE);
  delay(500);
  
  Serial.println("\nRed Dust Interactive Object");
  Serial.println("Supports: Serial (value,timestamp format) and OSC");
  Serial.println("==========================================");
  
  // Initialize display FIRST (before WiFi to show graph immediately)
  initializeDisplay();
  
  // Initialize WiFi Manager (non-blocking, after display is ready)
  initializeWiFi();
  
  // Reserve buffer space for serial communication
  serialBuffer.reserve(SERIAL_BUFFER_SIZE);
  
  // Initialize Serial state
  serialConnected = false;
  serialReceivingData = false;
  currentPWM = 0;
  hasPWMData = false;
  
  // Initialize vibration motor
  initializeVibrationMotor();
}

void loop() {
  // Process Serial messages FIRST (Serial has priority)
  processSerialMessages();
  
  // Update vibration motor based on received data
  updateVibrationMotor();
  
  // Process WiFi Manager (non-blocking, runs in parallel with Serial)
  wm.process();
  
  // Update WiFi connection status and initialize OSC if connected
  updateWiFiStatus();
  
  // Process OSC messages (non-blocking, runs in parallel with Serial)
  // Serial has priority, but OSC can still be processed when WiFi is connected
  if (wifiConnected) {
    processOSCMessages();
  }
  
  // Update status text display
  updateGui();
  
  // Debug: Print status every 100 iterations
  // loopCounter++;
  // if (loopCounter % 100 == 0) {
  //   Serial.printf("Loop running: iteration %lu, PWM=%d, hasData=%d, WiFi=%s\n", 
  //                 loopCounter, currentPWM, hasPWMData, wifiConnected ? "ON" : "OFF");
  // }
  
  // Small delay to prevent watchdog issues
  delay(1);
}

// TFT Display includes
#include <TFT_eSPI.h>
TFT_eSPI tft = TFT_eSPI();

#include <TFT_eWidget.h>               // Widget library

// WiFi Manager includes
// Fix for ESP32 3.x - include FS.h and bring FS into global namespace
#include <FS.h>
using fs::FS;
#include <WiFi.h>
#include <WiFiManager.h> // https://github.com/tzapu/WiFiManager
WiFiManager wm;

GraphWidget gr = GraphWidget(&tft);    // Graph widget gr instance with pointer to tft
TraceWidget tr = TraceWidget(&gr);     // Graph trace tr with pointer to gr

// Graph configuration
const float gxLow  = 0.0;
const float gxHigh = 200.0;            // X-axis: number of data points
const float gyLow  = 0.0;              // Y-axis: minimum value (0)
const float gyHigh = 1.0;              // Y-axis: maximum value (1.0 for normalized values)

// Graph state
float graphX = 0.0;                     // Current X position on graph
bool graphInitialized = false;

// Status display state
float latestValue = 0.0;                 // Latest received value for display
bool lastSerialConnected = false;        // Last connection state (for update detection)
bool lastSerialReceiving = false;       // Last receiving state (for update detection)
float lastDisplayedValue = -1.0;        // Last displayed value (for update detection)

// WiFi state
bool wifiConnected = false;              // Track WiFi connection status
bool lastWifiConnected = false;         // Last WiFi connection state (for update detection)
String lastWifiStatusText = "";         // Last WiFi status text displayed (for update detection)

// Configuration constants
#define VIBRATION_MOTOR_PIN 25  // PWM pin for vibration motor (GPIO 25 - safe for ESP32)
// Note: Avoid pins 0, 2, 4, 12-15, 25-27 if using display
// GPIO 25 is typically safe for PWM on TTGO T-Display

// PWM mapping configuration
#define PWM_MIN 0      // Minimum PWM value (motor off)
#define PWM_MAX 255    // Maximum PWM value (full intensity)

// ESP32 LEDC PWM configuration (for ESP32 Arduino core 3.x)
#define PWM_FREQUENCY 5000    // PWM frequency in Hz (5kHz is good for motors)
#define PWM_RESOLUTION 8      // 8-bit resolution (0-255)

// Serial communication configuration
String serialBuffer = "";
const int SERIAL_BUFFER_SIZE = 128;
const unsigned long SERIAL_TIMEOUT_MS = 1000;  // Message timeout
unsigned long lastSerialCharTime = 0;
bool serialConnected = false;  // Track if Serial port is open/connected (has received data)
bool serialReceivingData = false;  // Track if Serial is actively receiving data
const unsigned long SERIAL_RECEIVING_TIMEOUT = 100;  // Consider "receiving" if data within last 100ms

int currentPWM = 0;  // Current PWM value from Serial data
bool hasPWMData = false;  // Whether we have valid PWM data to output

// Loop iteration counter for debug messages
unsigned long loopCounter = 0;

// Function to map normalized value (0..1) to PWM value
int mapValueToPWM(float value) {
  // Constrain value to 0..1 range
  value = constrain(value, 0.0, 1.0);
  
  // Map value to PWM range (linear interpolation)
  int pwmValue = (int)(value * (PWM_MAX - PWM_MIN) + PWM_MIN);
  
  // Ensure result is within valid PWM range
  return constrain(pwmValue, PWM_MIN, PWM_MAX);
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
  
  // Store latest value for display
  latestValue = value;
  
  // Map value to PWM
  int pwmValue = mapValueToPWM(value);
  currentPWM = pwmValue;
  hasPWMData = true;
  serialReceivingData = true;  // Mark as currently receiving
  lastSerialCharTime = millis();  // Update timestamp
  
  Serial.printf("Received Serial: value=%.6f, PWM=%d\n", value, pwmValue);
  
  // Add point to graph if initialized
  if (graphInitialized) {
    tr.addPoint(graphX, value);
    graphX += 1.0;
    
    // If the end of the graph x axis is reached, reset and start a new trace
    if (graphX > gxHigh) {
      graphX = 0.0;
      
      // Draw empty graph to clear old one (positioned below status text)
      gr.drawGraph(10, 25);
      // Start new trace
      tr.startTrace(TFT_RED);
    }
  }
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

// Update status text display
void updateStatusText() {
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
  if (serialConnected != lastSerialConnected || 
      serialReceivingData != lastSerialReceiving ||
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
  
  // Center: Active status (centered around 120px)
  tft.setCursor(100, 5);
  if (serialReceivingData) {
    tft.setTextColor(TFT_CYAN, TFT_BLACK, true);
    tft.print("Active");
  } else {
    tft.setTextColor(TFT_YELLOW, TFT_BLACK, true);
    tft.print("Idle");
  }
  
  // Right: Latest value (right-aligned, starting around 170px)
  tft.setCursor(170, 5);
  tft.setTextColor(TFT_WHITE, TFT_BLACK, true);
  // tft.print("Val: ");
  tft.print(latestValue, 3);  // 3 decimal places
  
  // Update last displayed states
  lastSerialConnected = serialConnected;
  lastSerialReceiving = serialReceivingData;
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

void setup() {
  // Initialize serial communication
  Serial.begin(115200);
  delay(1000);
  Serial.println("\nArduino Vibration Motor Controller");
  Serial.println("Supports: Serial (value,timestamp format)");
  Serial.println("==========================================");
  
  // Initialize WiFi Manager
  WiFi.mode(WIFI_STA); // explicitly set mode, esp defaults to STA+AP
  
  // Configure WiFiManager for non-blocking operation
  wm.setConfigPortalBlocking(false);
  wm.setConfigPortalTimeout(60);
  
  // Automatically connect using saved credentials if they exist
  // If connection fails it starts an access point with the specified name
  if(wm.autoConnect("AutoConnectAP")){
    Serial.println("WiFi connected...yeey :)");
    wifiConnected = true;
  }
  else {
    Serial.println("WiFi Configportal running");
    wifiConnected = false;
  }
  
  // Initialize TFT display
  tft.init();
  tft.setRotation(3);  // Landscape orientation
  tft.fillScreen(TFT_BLACK);
  
  // Enable backlight (pin 4 for TTGO T-Display)
  pinMode(4, OUTPUT);
  digitalWrite(4, HIGH);
  
  // Graph area is 220 pixels wide, 110 pixels high, dark grey background
  // Reduced height to make room for status text at top
  gr.createGraph(220, 110, tft.color565(5, 5, 5));
  
  // X scale units is from 0 to 200 (data points), y scale units is 0 to 1 (normalized values)
  gr.setGraphScale(gxLow, gxHigh, gyLow, gyHigh);
  
  // X grid starts at 0 with lines every 20 x-scale units
  // Y grid starts at 0 with lines every 0.1 y-scale units
  // blue grid
  gr.setGraphGrid(gxLow, 20.0, gyLow, 0.1, TFT_BLUE);
  
  // Draw empty graph, top left corner at pixel coordinate 10,25 on TFT
  // Positioned below status text area (top 20 pixels)
  gr.drawGraph(10, 25);
  
  // Start a trace with red color
  tr.startTrace(TFT_RED);
  
  graphInitialized = true;
  graphX = 0.0;
  
  // Initialize status display
  latestValue = 0.0;
  lastSerialConnected = false;
  lastSerialReceiving = false;
  lastDisplayedValue = -1.0;
  lastWifiConnected = wifiConnected;  // Initialize WiFi status tracking
  lastWifiStatusText = "";  // Initialize WiFi status text tracking
  updateStatusText();  // Draw initial status
  
  // Reserve buffer space
  serialBuffer.reserve(SERIAL_BUFFER_SIZE);
  
  // Initialize Serial state
  serialConnected = false;
  serialReceivingData = false;
  currentPWM = 0;
  hasPWMData = false;
  
  // Initialize vibration motor pin with ESP32 LEDC PWM (ESP32 3.x API)
  // Attach pin to LEDC with frequency and resolution (auto-assigns channel)
  ledcAttach(VIBRATION_MOTOR_PIN, PWM_FREQUENCY, PWM_RESOLUTION);
  // Start with motor off
  ledcWrite(VIBRATION_MOTOR_PIN, 0);
  
  Serial.println("Vibration motor initialized on GPIO 25");
  Serial.println("TFT display and graph initialized");
}

void loop() {
  // Process Serial messages FIRST (Serial has priority)
  processSerialMessages();
  
  // Update vibration motor based on received data
  updateVibrationMotor();
  
  // Process WiFi Manager (non-blocking, runs in parallel with Serial)
  wm.process();
  
  // Update WiFi connection status
  bool currentWifiStatus = (WiFi.status() == WL_CONNECTED);
  if (currentWifiStatus != wifiConnected) {
    wifiConnected = currentWifiStatus;
    if (wifiConnected) {
      Serial.println("WiFi connected");
    } else {
      Serial.println("WiFi disconnected");
    }
  }
  
  // Update status text display
  updateStatusText();
  
  // Debug: Print status every 100 iterations
  // loopCounter++;
  // if (loopCounter % 100 == 0) {
  //   Serial.printf("Loop running: iteration %lu, PWM=%d, hasData=%d, WiFi=%s\n", 
  //                 loopCounter, currentPWM, hasPWMData, wifiConnected ? "ON" : "OFF");
  // }
  
  // Small delay to prevent watchdog issues
  delay(1);
}

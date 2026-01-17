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
  
  // Map value to PWM
  int pwmValue = mapValueToPWM(value);
  currentPWM = pwmValue;
  hasPWMData = true;
  serialReceivingData = true;  // Mark as currently receiving
  lastSerialCharTime = millis();  // Update timestamp
  
  Serial.printf("Received Serial: value=%.6f, PWM=%d\n", value, pwmValue);
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
}

void loop() {
  // Process Serial messages
  processSerialMessages();
  
  // Update vibration motor based on received data
  updateVibrationMotor();
  
  // Debug: Print status every 100 iterations
  loopCounter++;
  if (loopCounter % 100 == 0) {
    Serial.printf("Loop running: iteration %lu, PWM=%d, hasData=%d\n", 
                  loopCounter, currentPWM, hasPWMData);
  }
  
  // Small delay to prevent watchdog issues
  delay(1);
}

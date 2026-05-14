// Serial wire format matches RDCC: v1,v2,...,vN,timestamp (last comma = timestamp).
// Values in [0, 1] are live levels; outside that range = inactive/padding (motor off).
// This board drives one motor from Pin_A only (first float v1).

// Configuration constants
#define VIBRATION_MOTOR_PIN 9  // PWM pin for vibration motor (change as needed)

// PWM mapping configuration
#define PWM_MIN 0      // Minimum PWM value (motor off)
#define PWM_MAX 255    // Maximum PWM value (full intensity)

// Serial communication configuration
#define SERIAL_BAUD_RATE 115200  // Serial communication baud rate

String serialBuffer = "";
const int SERIAL_BUFFER_SIZE = 128;
const unsigned long SERIAL_TIMEOUT_MS = 1000;  // Message timeout
unsigned long lastSerialCharTime = 0;
bool serialConnected = false;  // Track if Serial port is open/connected (has received data)
bool serialReceivingData = false;  // Track if Serial is actively receiving data
const unsigned long SERIAL_RECEIVING_TIMEOUT = 100;  // Consider "receiving" if data within last 100ms

int currentPWM = 0;  // Current PWM value from Serial data
bool hasPWMData = false;  // Whether we have valid PWM data to output

// Function to map normalized value (0..1) to PWM value
int mapValueToPWM(float value) {
  // Constrain value to 0..1 range
  value = constrain(value, 0.0, 1.0);
  
  // Map value to PWM range (linear interpolation)
  int pwmValue = (int)(value * (PWM_MAX - PWM_MIN) + PWM_MIN);
  
  // Ensure result is within valid PWM range
  return constrain(pwmValue, PWM_MIN, PWM_MAX);
}

// Handle Pin_A wire value (first float in bundle). Inactive if outside [0, 1].
void handleSerialValue(float value, const String& /*timestamp*/) {
  if (isnan(value) || isinf(value)) {
    Serial.println("Error: Invalid value (NaN or infinity), ignoring");
    return;
  }

  serialReceivingData = true;
  lastSerialCharTime = millis();

  if (value < 0.0f || value > 1.0f) {
    currentPWM = 0;
    hasPWMData = true;
    Serial.printf("Serial: inactive/padding value=%.6f -> PWM off\n", value);
    return;
  }

  value = constrain(value, 0.0f, 1.0f);
  int pwmValue = mapValueToPWM(value);
  currentPWM = pwmValue;
  hasPWMData = true;

  Serial.printf("Received Serial: value=%.6f, PWM=%d\n", value, pwmValue);
}

// Process Serial message: ... ,timestamp (last comma). First value token = Pin_A.
void processSerialMessage(const String& message) {
  int lastComma = message.lastIndexOf(',');
  if (lastComma <= 0 || lastComma >= (int)message.length() - 1) {
    return;
  }

  String timestamp = message.substring(lastComma + 1);
  timestamp.trim();
  if (timestamp.length() == 0) {
    return;
  }

  String valuesPart = message.substring(0, lastComma);
  valuesPart.trim();
  if (valuesPart.length() == 0) {
    return;
  }

  int firstInnerComma = valuesPart.indexOf(',');
  String valueStr =
      (firstInnerComma < 0) ? valuesPart : valuesPart.substring(0, firstInnerComma);
  valueStr.trim();
  if (valueStr.length() == 0) {
    return;
  }

  float value = valueStr.toFloat();
  handleSerialValue(value, timestamp);
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
    // We have PWM data - output it
    analogWrite(VIBRATION_MOTOR_PIN, currentPWM);
  } else {
    // No data yet - turn off motor
    analogWrite(VIBRATION_MOTOR_PIN, 0);
  }
}

void setup() {
  // Initialize serial communication
  Serial.begin(SERIAL_BAUD_RATE);
  delay(1000);
  
  Serial.println("\nArduino Vibration Motor Controller");
  Serial.println("Serial: v1[,v2,...],timestamp — uses v1 (Pin_A); [0,1]=live, else off");
  Serial.println("==========================================");
  
  // Reserve buffer space
  serialBuffer.reserve(SERIAL_BUFFER_SIZE);
  
  // Initialize Serial state
  serialConnected = false;
  serialReceivingData = false;
  currentPWM = 0;
  hasPWMData = false;
  
  // Initialize vibration motor pin
  pinMode(VIBRATION_MOTOR_PIN, OUTPUT);
  analogWrite(VIBRATION_MOTOR_PIN, 0);  // Start with motor off
}

void loop() {
  // Process Serial messages
  processSerialMessages();
  
  // Update vibration motor based on received data
  updateVibrationMotor();
  
  // Small delay to prevent watchdog issues
  delay(1);
}

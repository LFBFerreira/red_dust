#include <SoftwareSerial.h>

// Configuration constants
#define VIBRATION_MOTOR_PIN_CH1 9   // PWM pin for channel 1 output
#define VIBRATION_MOTOR_PIN_CH2 10  // PWM pin for channel 2 output

// PWM mapping configuration
#define PWM_MIN 0      // Minimum PWM value (motor off)
#define PWM_MAX 255    // Maximum PWM value (full intensity)

// Serial communication configuration
#define SERIAL_BAUD_RATE 115200            // USB serial communication baud rate
#define AUX_SERIAL_BAUD_RATE 9600          // SoftwareSerial baud rate (stable on Uno)
#define AUX_SERIAL_RX_PIN 2                // SoftwareSerial RX pin (input channel 2)
#define AUX_SERIAL_TX_PIN 3                // SoftwareSerial TX pin (unused, required by library)

SoftwareSerial auxSerial(AUX_SERIAL_RX_PIN, AUX_SERIAL_TX_PIN);

const int SERIAL_BUFFER_SIZE = 128;
const unsigned long SERIAL_TIMEOUT_MS = 1000;  // Message timeout
const unsigned long SERIAL_RECEIVING_TIMEOUT = 100;  // Consider "receiving" if data within last 100ms

struct InputChannelState {
  String serialBuffer;
  unsigned long lastSerialCharTime;
  bool serialConnected;
  bool serialReceivingData;
  int currentPWM;
  bool hasPWMData;
  uint8_t outputPin;
  const char* label;
};

InputChannelState channel1 = {"", 0, false, false, 0, false, VIBRATION_MOTOR_PIN_CH1, "CH1(USB)"};
InputChannelState channel2 = {"", 0, false, false, 0, false, VIBRATION_MOTOR_PIN_CH2, "CH2(AUX)"};

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
void handleSerialValue(InputChannelState &channel, float value, const String &timestamp) {
  // Validate value is a valid number (not NaN or infinity)
  if (isnan(value) || isinf(value)) {
    Serial.println("Error: Invalid value (NaN or infinity), ignoring");
    return;
  }
  
  // Clamp value to 0..1 range
  value = constrain(value, 0.0, 1.0);
  
  // Map value to PWM
  int pwmValue = mapValueToPWM(value);
  channel.currentPWM = pwmValue;
  channel.hasPWMData = true;
  channel.serialReceivingData = true;  // Mark as currently receiving
  channel.lastSerialCharTime = millis();  // Update timestamp

  Serial.print("Received ");
  Serial.print(channel.label);
  Serial.print(": value=");
  Serial.print(value, 6);
  Serial.print(", PWM=");
  Serial.print(pwmValue);
  Serial.print(", ts=");
  Serial.println(timestamp);
}

void handleDualSerialValues(float value1, float value2, const String &timestamp) {
  handleSerialValue(channel1, value1, timestamp);
  handleSerialValue(channel2, value2, timestamp);
}

// Process Serial message
void processSerialMessage(const String &message, InputChannelState &channel) {
  int commaIndex = message.indexOf(',');
  
  if (commaIndex <= 0 || commaIndex >= message.length() - 1) {
    // Invalid message format
    return;
  }

  int secondCommaIndex = message.indexOf(',', commaIndex + 1);
  if (secondCommaIndex > commaIndex && secondCommaIndex < message.length() - 1) {
    // Dual channel format: value1,value2,timestamp
    String value1Str = message.substring(0, commaIndex);
    String value2Str = message.substring(commaIndex + 1, secondCommaIndex);
    String timestamp = message.substring(secondCommaIndex + 1);
    value1Str.trim();
    value2Str.trim();

    float value1 = value1Str.toFloat();
    float value2 = value2Str.toFloat();
    bool value1Valid = value1Str.length() > 0 &&
      (value1Str.indexOf('.') >= 0 || value1Str.toInt() != 0 || value1Str == "0" || value1Str == "0.0") &&
      value1 >= -1000.0 && value1 <= 1000.0;
    bool value2Valid = value2Str.length() > 0 &&
      (value2Str.indexOf('.') >= 0 || value2Str.toInt() != 0 || value2Str == "0" || value2Str == "0.0") &&
      value2 >= -1000.0 && value2 <= 1000.0;

    if (value1Valid && value2Valid) {
      handleDualSerialValues(value1, value2, timestamp);
    } else {
      Serial.print("Error: Invalid dual serial value format: '");
      Serial.print(message);
      Serial.println("'");
    }
    return;
  }

  // Single channel format: value,timestamp
  String valueStr = message.substring(0, commaIndex);
  String timestamp = message.substring(commaIndex + 1);
  valueStr.trim();
  if (valueStr.length() == 0) {
    return;
  }

  float value = valueStr.toFloat();
  if (valueStr.length() > 0 &&
      (valueStr.indexOf('.') >= 0 || valueStr.toInt() != 0 || valueStr == "0" || valueStr == "0.0") &&
      value >= -1000.0 && value <= 1000.0) {
    handleSerialValue(channel, value, timestamp);
  } else {
    Serial.print("Error: Invalid serial value format on ");
    Serial.print(channel.label);
    Serial.print(": '");
    Serial.print(valueStr);
    Serial.println("'");
  }
}

// Process incoming Serial messages
void processSerialMessages(Stream &input, InputChannelState &channel) {
  // Read all available serial data first
  if (input.available() > 0) {
    channel.lastSerialCharTime = millis();
    channel.serialConnected = true;  // Mark as connected (has received data)
    channel.serialReceivingData = true;  // Currently receiving data
    
    // Read all available characters, accumulating into serialBuffer
    while (input.available() > 0) {
      char c = input.read();
      
      if (c == '\n' || c == '\r') {
        // End of message - add newline marker to buffer
        channel.serialBuffer += '\n';
      } else if (c >= 32 && c <= 126) {  // Printable ASCII only
        channel.serialBuffer += c;
        
        // Buffer overflow protection
        if (channel.serialBuffer.length() >= SERIAL_BUFFER_SIZE - 1) {
          channel.serialBuffer = "";
        }
      }
    }
    
    // Find and process only the latest complete message
    // Look for the last newline in the buffer
    int lastNewline = channel.serialBuffer.lastIndexOf('\n');
    
    if (lastNewline >= 0) {
      // We have at least one complete message
      // Find the start of the last message (previous newline or start of buffer)
      int messageStart = 0;
      for (int i = lastNewline - 1; i >= 0; i--) {
        if (channel.serialBuffer.charAt(i) == '\n') {
          messageStart = i + 1;
          break;
        }
      }
      
      // Extract the latest complete message (between messageStart and lastNewline)
      String latestMessage = channel.serialBuffer.substring(messageStart, lastNewline);
      
      if (latestMessage.length() > 0) {
        processSerialMessage(latestMessage, channel);
      }
      
      // Clear buffer after processing latest message
      // If there's any data after the last newline, keep it (incomplete message)
      if (lastNewline < channel.serialBuffer.length() - 1) {
        channel.serialBuffer = channel.serialBuffer.substring(lastNewline + 1);
      } else {
        channel.serialBuffer = "";
      }
    }
    // If no newline found, keep the buffer for next iteration (incomplete message)
  }
  
  // Check if we're still "receiving" (data within last 100ms)
  if (channel.serialReceivingData && (millis() - channel.lastSerialCharTime) > SERIAL_RECEIVING_TIMEOUT) {
    channel.serialReceivingData = false;
  }
  
  // Timeout: clear buffer if no data received for a while
  if (channel.serialBuffer.length() > 0 && 
      (millis() - channel.lastSerialCharTime) > SERIAL_TIMEOUT_MS) {
    channel.serialBuffer = "";
  }
}

// Check if Serial is connected (has received data)
bool isSerialConnected(const InputChannelState &channel) {
  return channel.serialConnected;
}

// Check if Serial is actively receiving data
bool isSerialReceiving(const InputChannelState &channel) {
  return channel.serialReceivingData;
}

// Update vibration motor PWM based on received data
void updateVibrationMotor(const InputChannelState &channel) {
  if (channel.hasPWMData) {
    // We have PWM data - output it
    analogWrite(channel.outputPin, channel.currentPWM);
  } else {
    // No data yet - turn off motor
    analogWrite(channel.outputPin, 0);
  }
}

void setup() {
  // Initialize serial communication
  Serial.begin(SERIAL_BAUD_RATE);
  auxSerial.begin(AUX_SERIAL_BAUD_RATE);
  delay(1000);
  
  Serial.println("\nArduino Vibration Motor Controller");
  Serial.println("Supports:");
  Serial.println("  CH1: USB Serial (value,timestamp) -> PWM pin 9");
  Serial.println("  CH2: AUX SoftwareSerial RX pin 2 (value,timestamp) -> PWM pin 10");
  Serial.println("==========================================");
  
  // Reserve buffer space and reset channel states
  channel1.serialBuffer.reserve(SERIAL_BUFFER_SIZE);
  channel2.serialBuffer.reserve(SERIAL_BUFFER_SIZE);
  channel1.serialConnected = false;
  channel1.serialReceivingData = false;
  channel1.currentPWM = 0;
  channel1.hasPWMData = false;
  channel2.serialConnected = false;
  channel2.serialReceivingData = false;
  channel2.currentPWM = 0;
  channel2.hasPWMData = false;
  
  // Initialize vibration motor pins
  pinMode(VIBRATION_MOTOR_PIN_CH1, OUTPUT);
  pinMode(VIBRATION_MOTOR_PIN_CH2, OUTPUT);
  analogWrite(VIBRATION_MOTOR_PIN_CH1, 0);  // Start with motor off
  analogWrite(VIBRATION_MOTOR_PIN_CH2, 0);  // Start with motor off
}

void loop() {
  // Process both input channels
  processSerialMessages(Serial, channel1);
  processSerialMessages(auxSerial, channel2);
  
  // Update both outputs based on received data
  updateVibrationMotor(channel1);
  updateVibrationMotor(channel2);
  
  // Small delay to prevent watchdog issues
  delay(1);
}

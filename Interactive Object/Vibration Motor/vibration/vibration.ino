// Serial wire format matches RDCC: v1,v2,...,vN,timestamp (last comma = timestamp).
// Values in [0, 1] are live levels per slot (Pin_A, Pin_B, ...); outside [0,1] =
// inactive/padding for that slot (PWM off). Missing tail slots are treated as 0.0 (off).

// --- Multi-pin (align count/order with Red Dust Control Center Pin_A..Pin_E, max 5) ---
#define MAX_PINS 5
// AVR PWM-capable pins on typical Uno/Nano: 3,5,6,9,10,11 — edit for your wiring/board.
static const uint8_t OUTPUT_PINS[MAX_PINS] = {9, 10, 11, 5, 6};

// PWM mapping configuration
#define PWM_MIN 0      // Minimum PWM value (motor off)
#define PWM_MAX 255    // Maximum PWM value (full intensity)

// Serial communication configuration
#define SERIAL_BAUD_RATE 115200  // Serial communication baud rate

String serialBuffer = "";
const int SERIAL_BUFFER_SIZE = 384;
const unsigned long SERIAL_TIMEOUT_MS = 1000;  // Message timeout
unsigned long lastSerialCharTime = 0;
bool serialConnected = false;
bool serialReceivingData = false;
const unsigned long SERIAL_RECEIVING_TIMEOUT = 100;

int pwmValues[MAX_PINS] = {0};
bool hasPWMData = false;

int mapValueToPWM(float value) {
  value = constrain(value, 0.0f, 1.0f);
  int pwmValue = (int)(value * (PWM_MAX - PWM_MIN) + PWM_MIN);
  return constrain(pwmValue, PWM_MIN, PWM_MAX);
}

bool parseFloatToken(const String& token, float* out) {
  if (token.length() == 0) {
    *out = 0.0f;
    return false;
  }
  float v = token.toFloat();
  if (isnan(v) || isinf(v)) {
    *out = 0.0f;
    return false;
  }
  *out = v;
  return true;
}

// Apply one frame: incoming[0..incomingCount-1] maps to Pin_A..; extras ignored.
void applyPinFrame(const float* incoming, int incomingCount) {
  serialReceivingData = true;
  lastSerialCharTime = millis();

  if (incomingCount < 0) {
    incomingCount = 0;
  }
  if (incomingCount > MAX_PINS) {
    incomingCount = MAX_PINS;
  }

  for (int i = 0; i < MAX_PINS; i++) {
    float v = (incoming != nullptr && i < incomingCount) ? incoming[i] : 0.0f;
    if (isnan(v) || isinf(v)) {
      v = 0.0f;
    }
    if (v < 0.0f || v > 1.0f) {
      pwmValues[i] = 0;
      continue;
    }
    v = constrain(v, 0.0f, 1.0f);
    pwmValues[i] = mapValueToPWM(v);
  }
  hasPWMData = true;
}

void handleSerialFrame(const float* values, int count, const String& /*timestamp*/) {
  applyPinFrame(values, count);
}

// Serial line: v1,v2,...,vN,timestamp  (last comma separates timestamp)
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

  float values[MAX_PINS];
  int n = 0;
  int start = 0;
  for (int i = 0; i <= (int)valuesPart.length(); i++) {
    if (i == (int)valuesPart.length() || valuesPart.charAt(i) == ',') {
      String token = valuesPart.substring(start, i);
      token.trim();
      if (token.length() > 0) {
        float v;
        parseFloatToken(token, &v);
        if (n < MAX_PINS) {
          values[n++] = v;
        }
        // tokens beyond MAX_PINS ignored (sender may send wider bundle)
      }
      start = i + 1;
    }
  }

  if (n == 0) {
    return;
  }

  handleSerialFrame(values, n, timestamp);
}

void processSerialMessages() {
  if (Serial.available() > 0) {
    lastSerialCharTime = millis();
    serialConnected = true;
    serialReceivingData = true;

    while (Serial.available() > 0) {
      char c = Serial.read();

      if (c == '\n' || c == '\r') {
        serialBuffer += '\n';
      } else if (c >= 32 && c <= 126) {
        serialBuffer += c;
        if ((int)serialBuffer.length() >= SERIAL_BUFFER_SIZE - 1) {
          serialBuffer = "";
        }
      }
    }

    int lastNewline = serialBuffer.lastIndexOf('\n');
    if (lastNewline >= 0) {
      int messageStart = 0;
      for (int i = lastNewline - 1; i >= 0; i--) {
        if (serialBuffer.charAt(i) == '\n') {
          messageStart = i + 1;
          break;
        }
      }

      String latestMessage = serialBuffer.substring(messageStart, lastNewline);
      if (latestMessage.length() > 0) {
        processSerialMessage(latestMessage);
      }

      if (lastNewline < (int)serialBuffer.length() - 1) {
        serialBuffer = serialBuffer.substring(lastNewline + 1);
      } else {
        serialBuffer = "";
      }
    }
  }

  if (serialReceivingData && (millis() - lastSerialCharTime) > SERIAL_RECEIVING_TIMEOUT) {
    serialReceivingData = false;
  }

  if (serialBuffer.length() > 0 &&
      (millis() - lastSerialCharTime) > SERIAL_TIMEOUT_MS) {
    serialBuffer = "";
  }
}

bool isSerialConnected() {
  return serialConnected;
}

bool isSerialReceiving() {
  return serialReceivingData;
}

void updateVibrationMotors() {
  if (!hasPWMData) {
    for (int i = 0; i < MAX_PINS; i++) {
      analogWrite(OUTPUT_PINS[i], 0);
    }
    return;
  }
  for (int i = 0; i < MAX_PINS; i++) {
    analogWrite(OUTPUT_PINS[i], pwmValues[i]);
  }
}

void setup() {
  Serial.begin(SERIAL_BAUD_RATE);
  delay(1000);

  Serial.println(F("\nArduino Vibration Motor Controller (multi-pin)"));
  Serial.println(F("Serial: v1[,v2,...],timestamp — Pin_A..E -> OUTPUT_PINS[]"));
  Serial.println(F("[0,1] = live level; outside = inactive; max 5 slots"));
  Serial.println(F("=========================================="));

  serialBuffer.reserve(SERIAL_BUFFER_SIZE);

  serialConnected = false;
  serialReceivingData = false;
  hasPWMData = false;
  for (int i = 0; i < MAX_PINS; i++) {
    pwmValues[i] = 0;
    pinMode(OUTPUT_PINS[i], OUTPUT);
    analogWrite(OUTPUT_PINS[i], 0);
  }
}

void loop() {
  processSerialMessages();
  updateVibrationMotors();
  delay(1);
}

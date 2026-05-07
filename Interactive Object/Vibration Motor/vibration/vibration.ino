// Forward declaration to satisfy Arduino's auto-prototype generation
struct InputChannelState;

// Configuration constants
// Mode B (LilyGO T-Display ESP32 + MAX9744 + Dayton exciter)
// - CH1 drives audio amplitude via ESP32 DAC -> MAX9744 line input
// - CH2 drives vibration motor via PWM (LEDC)
//
// Avoid TFT pins (given): 4, 5, 16, 18, 19, 23
// Avoid common strapping pins for external hardware if possible: 0, 2, 12, 15
#define AUDIO_DAC_PIN 25              // ESP32 DAC1 (analog out) -> MAX9744 INL/INR
#define VIBRATION_MOTOR_PIN_CH2 32    // PWM pin for channel 2 output (motor driver input)

// PWM mapping configuration
#define PWM_MIN 0      // Minimum PWM value (motor off)
#define PWM_MAX 255    // Maximum PWM value (full intensity)

// Serial communication configuration
#define SERIAL_BAUD_RATE 115200            // USB serial communication baud rate
#define AUX_SERIAL_BAUD_RATE 9600          // AUX UART baud rate
#define AUX_SERIAL_RX_PIN 27               // AUX UART RX pin (avoid TFT pins / I2C pins)
#define AUX_SERIAL_TX_PIN 13               // AUX UART TX pin (can be unused)

// MAX9744 volume control (I2C)
// Typical default address is 0x4B. Volume is a single byte 0..63.
#include <Wire.h>
#define MAX9744_I2C_ADDR 0x4B
#define I2C_SDA_PIN 21
#define I2C_SCL_PIN 22
#define MAX9744_DEFAULT_VOLUME 40  // 0..63

// Use a hardware UART on ESP32-S3 (SoftwareSerial not needed/recommended)
HardwareSerial auxSerial(1);

// ESP32 LEDC PWM configuration
static const int PWM_FREQ_HZ = 5000;
static const int PWM_RES_BITS = 8;  // 0..255
static const int LEDC_CHANNEL_CH1 = 0;
static const int LEDC_CHANNEL_CH2 = 1;

// LEDC API compatibility:
// - esp32 core v2.x: ledcSetup/ledcAttachPin/ledcWrite(channel, duty)
// - esp32 core v3.x: ledcAttach(pin, freq, resolution) / ledcWrite(pin, duty)
#include <esp_arduino_version.h>
#include <math.h>

// Audio mode (B1): sine tone on DAC with amplitude controlled by CH1.
enum OutputMode : uint8_t { MODE_TACTILE = 0, MODE_AUDIO = 1 };
volatile OutputMode g_mode = MODE_TACTILE;

static const uint32_t AUDIO_SAMPLE_RATE_HZ = 8000;
static const uint16_t SINE_TABLE_SIZE = 256;
static uint8_t g_sine_table[SINE_TABLE_SIZE];
volatile uint32_t g_phase = 0;
volatile uint32_t g_phase_inc = 0;
volatile uint8_t g_amp = 0;  // 0..255 envelope from CH1

hw_timer_t *g_audio_timer = nullptr;
portMUX_TYPE g_audio_timer_mux = portMUX_INITIALIZER_UNLOCKED;

static inline void audioSetFreqHz(uint16_t hz) {
  if (hz < 20) hz = 20;
  if (hz > 2000) hz = 2000;
  uint64_t inc = ((uint64_t)hz << 32) / (uint64_t)AUDIO_SAMPLE_RATE_HZ;
  portENTER_CRITICAL(&g_audio_timer_mux);
  g_phase_inc = (uint32_t)inc;
  portEXIT_CRITICAL(&g_audio_timer_mux);
}

void IRAM_ATTR onAudioTimerISR() {
  uint32_t phase = g_phase + g_phase_inc;
  g_phase = phase;
  uint8_t idx = (uint8_t)(phase >> 24);
  uint8_t s = g_sine_table[idx];  // 0..255 centered at ~128
  uint8_t a = g_amp;              // 0..255
  int16_t centered = (int16_t)s - 128;
  int16_t scaled = (int16_t)((centered * (int16_t)a) / 255);
  uint8_t out = (uint8_t)(scaled + 128);
  dacWrite(AUDIO_DAC_PIN, out);
}

static inline void audioStart() {
  if (g_audio_timer != nullptr) return;
#if ESP_ARDUINO_VERSION_MAJOR >= 3
  // Core v3.x timer API
  // Configure timer to tick at sample rate, then alarm every tick.
  g_audio_timer = timerBegin(AUDIO_SAMPLE_RATE_HZ);
  timerAttachInterrupt(g_audio_timer, &onAudioTimerISR);
  timerAlarm(g_audio_timer, 1, true, 0); // alarm_value=1 tick, autoreload, unlimited
#else
  // Core v2.x timer API
  // 80MHz APB clock / 80 = 1MHz timer tick (1us)
  g_audio_timer = timerBegin(0, 80, true);
  timerAttachInterrupt(g_audio_timer, &onAudioTimerISR, true);
  timerAlarmWrite(g_audio_timer, 1000000 / AUDIO_SAMPLE_RATE_HZ, true);
  timerAlarmEnable(g_audio_timer);
#endif
}

static inline void audioStop() {
  if (g_audio_timer == nullptr) return;
#if ESP_ARDUINO_VERSION_MAJOR >= 3
  timerStop(g_audio_timer);
  timerDetachInterrupt(g_audio_timer);
  timerEnd(g_audio_timer);
#else
  timerAlarmDisable(g_audio_timer);
  timerDetachInterrupt(g_audio_timer);
  timerEnd(g_audio_timer);
#endif
  g_audio_timer = nullptr;
  dacWrite(AUDIO_DAC_PIN, 0);
}

static inline void pwmAttach(uint8_t pin, uint8_t channel) {
#if ESP_ARDUINO_VERSION_MAJOR >= 3
  (void)channel;
  ledcAttach(pin, PWM_FREQ_HZ, PWM_RES_BITS);
#else
  ledcSetup(channel, PWM_FREQ_HZ, PWM_RES_BITS);
  ledcAttachPin(pin, channel);
#endif
}

static inline void pwmWrite(uint8_t pin, uint8_t channel, int duty) {
  duty = constrain(duty, PWM_MIN, PWM_MAX);
#if ESP_ARDUINO_VERSION_MAJOR >= 3
  (void)channel;
  ledcWrite(pin, duty);
#else
  (void)pin;
  ledcWrite(channel, duty);
#endif
}

static inline void max9744SetVolume(uint8_t vol) {
  if (vol > 63) vol = 63;
  Wire.beginTransmission(MAX9744_I2C_ADDR);
  Wire.write(vol); // single byte command
  Wire.endTransmission();
}

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
  uint8_t ledcChannel;
  const char* label;
};

// CH1 uses DAC (so ledcChannel is unused there)
InputChannelState channel1 = {"", 0, false, false, 0, false, AUDIO_DAC_PIN, LEDC_CHANNEL_CH1, "CH1(USB->AUDIO)"};
InputChannelState channel2 = {"", 0, false, false, 0, false, VIBRATION_MOTOR_PIN_CH2, LEDC_CHANNEL_CH2, "CH2(AUX->MOTOR)"};

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
  // Mode command: "MODE,AUD" or "MODE,TAC"
  if (message.startsWith("MODE,") || message.startsWith("MODE=")) {
    int sep = message.indexOf(',');
    if (sep < 0) sep = message.indexOf('=');
    if (sep > 0 && sep < (int)message.length() - 1) {
      String modeStr = message.substring(sep + 1);
      modeStr.trim();
      modeStr.toUpperCase();
      if (modeStr == "AUD" || modeStr == "AUDIO") {
        g_mode = MODE_AUDIO;
        audioStart();
        Serial.println("Mode set to AUDIO (tone on DAC, CH1=amplitude)");
      } else if (modeStr == "TAC" || modeStr == "TACTILE") {
        g_mode = MODE_TACTILE;
        audioStop();
        Serial.println("Mode set to TACTILE (DAC level follows CH1)");
      }
    }
    return;
  }

  // Frequency command (Hz): "FREQ,120" or "FREQ=200"
  if (message.startsWith("FREQ,") || message.startsWith("FREQ=")) {
    int sep = message.indexOf(',');
    if (sep < 0) sep = message.indexOf('=');
    if (sep > 0 && sep < (int)message.length() - 1) {
      String fStr = message.substring(sep + 1);
      fStr.trim();
      int hz = fStr.toInt();
      if (fStr.length() > 0 && hz > 0) {
        audioSetFreqHz((uint16_t)hz);
        Serial.print("Tone frequency set to ");
        Serial.print(hz);
        Serial.println(" Hz");
      }
    }
    return;
  }

  // Volume command (USB or AUX): "VOL,0..63" or "VOL=0..63"
  if (message.startsWith("VOL,") || message.startsWith("VOL=")) {
    int sep = message.indexOf(',');
    if (sep < 0) sep = message.indexOf('=');
    if (sep > 0 && sep < (int)message.length() - 1) {
      String volStr = message.substring(sep + 1);
      volStr.trim();
      int vol = volStr.toInt();
      if (volStr.length() > 0 && vol >= 0 && vol <= 63) {
        max9744SetVolume((uint8_t)vol);
        Serial.print("MAX9744 volume set to ");
        Serial.println(vol);
      }
    }
    return;
  }

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
    // Stop output when data stream becomes stale
    channel.currentPWM = 0;
    channel.hasPWMData = false;
  }
  
  // Timeout: clear buffer if no data received for a while
  if (channel.serialBuffer.length() > 0 && 
      (millis() - channel.lastSerialCharTime) > SERIAL_TIMEOUT_MS) {
    channel.serialBuffer = "";
  }

  // Consider channel disconnected after a longer silence
  if (channel.serialConnected &&
      (millis() - channel.lastSerialCharTime) > SERIAL_TIMEOUT_MS) {
    channel.serialConnected = false;
    channel.serialReceivingData = false;
    channel.currentPWM = 0;
    channel.hasPWMData = false;
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
    // CH1 is AUDIO (DAC), CH2 is MOTOR (PWM)
    if (channel.outputPin == AUDIO_DAC_PIN) {
      g_amp = (uint8_t)channel.currentPWM;
      if (g_mode == MODE_TACTILE) {
        dacWrite(AUDIO_DAC_PIN, (uint8_t)channel.currentPWM);
      }
    } else {
      pwmWrite(channel.outputPin, channel.ledcChannel, channel.currentPWM);
    }
  } else {
    // No data yet - turn off motor
    if (channel.outputPin == AUDIO_DAC_PIN) {
      g_amp = 0;
      if (g_mode == MODE_TACTILE) {
        dacWrite(AUDIO_DAC_PIN, 0);
      }
    } else {
      pwmWrite(channel.outputPin, channel.ledcChannel, 0);
    }
  }
}

void setup() {
  // Initialize serial communication
  Serial.begin(SERIAL_BAUD_RATE);
  auxSerial.begin(AUX_SERIAL_BAUD_RATE, SERIAL_8N1, AUX_SERIAL_RX_PIN, AUX_SERIAL_TX_PIN);
  delay(1000);

  // I2C for MAX9744 volume control
  Wire.begin(I2C_SDA_PIN, I2C_SCL_PIN);
  max9744SetVolume(MAX9744_DEFAULT_VOLUME);

  // Build sine table once (256 samples)
  for (int i = 0; i < (int)SINE_TABLE_SIZE; i++) {
    float phase = (2.0f * (float)M_PI * (float)i) / (float)SINE_TABLE_SIZE;
    float s = sinf(phase); // -1..1
    int v = (int)(128.0f + 127.0f * s);
    if (v < 0) v = 0;
    if (v > 255) v = 255;
    g_sine_table[i] = (uint8_t)v;
  }
  audioSetFreqHz(120); // default tone frequency
  
  Serial.println("\nESP32 (LilyGO T-Display) Exciter + Motor Controller");
  Serial.println("Supports:");
  Serial.println("  CH1: USB Serial (value,timestamp) -> DAC GPIO 25 -> MAX9744 IN");
  Serial.println("  CH2: AUX UART RX GPIO 27 (value,timestamp) -> PWM GPIO 32");
  Serial.println("  Volume: send 'VOL,0..63' over USB/AUX");
  Serial.println("  Mode: send 'MODE,AUD' (tone) or 'MODE,TAC' (level)");
  Serial.println("  Tone: send 'FREQ,Hz' (e.g. FREQ,120)");
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
  
  // Initialize output pins
  pinMode(AUDIO_DAC_PIN, OUTPUT);
  pinMode(VIBRATION_MOTOR_PIN_CH2, OUTPUT);

  // Configure LEDC PWM
  pwmAttach(VIBRATION_MOTOR_PIN_CH2, LEDC_CHANNEL_CH2);

  // Start with outputs off
  dacWrite(AUDIO_DAC_PIN, 0);
  pwmWrite(VIBRATION_MOTOR_PIN_CH2, LEDC_CHANNEL_CH2, 0);
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

#include "settings.h"
#include "helpers.h"
#include "input.h"
#include "ui.h"
#include "i2s_audio.h"
#include "tactile_output.h"

#include <WiFi.h>
#include <WiFiUdp.h>
#include <WiFiManager.h>

// =============================================================================
// Shared state (both boards)
// =============================================================================

WiFiManager wm;
WiFiUDP udp;

static float latestPinValues[MAX_PINS] = {0};
static bool hasLiveData = false;
static bool wifiConnected = false;

// =============================================================================
// Outputs (common)
// =============================================================================

static void clearLivePinValues() {
  for (int i = 0; i < MAX_PINS; i++) {
    latestPinValues[i] = 0.0f;
  }
  hasLiveData = false;
}

static void pushOutputs() {
#if ENABLE_TACTILE_OUTPUT
  for (int i = 0; i < MAX_PINS; i++) {
    tactile_output_set_level(i, scaleShakeLevel(latestPinValues[i]));
  }
  tactile_output_apply(hasLiveData);
#endif
#if ENABLE_I2S_PCM5102
  if (hasLiveData) {
    i2s_audio_set_stereo_levels(scaleShakeLevel(latestPinValues[I2S_LEFT_PIN_INDEX]),
                                scaleShakeLevel(latestPinValues[I2S_RIGHT_PIN_INDEX]));
  } else {
    i2s_audio_mute();
  }
#endif
}

static void silenceOutputsOnStreamIdle() {
  if (input_streamActive() || !hasLiveData) {
    return;
  }
  clearLivePinValues();
  pushOutputs();
}

static void setShakeCarrierHz(float hz) {
#if ENABLE_I2S_PCM5102
  i2s_audio_set_carrier_hz(hz);
  serialDebugPrintf("PCM5102 carrier fixed to %.0f Hz (OSC still scales volume)\n", (double)hz);
#endif
#if ENABLE_TACTILE_OUTPUT
  tactile_output_set_carrier_hz(hz);
  serialDebugPrintf("PWM tactile carrier set to %.0f Hz\n",
                    (double)tactile_output_get_carrier_hz());
#endif
}

// Apply one frame: incoming[0..count-1]; [0,1] = live; out of range = inactive.
static void applyPinFrame(const float* incoming, int incomingCount) {
  if (incomingCount < 0) {
    incomingCount = 0;
  }
  if (incomingCount > MAX_PINS) {
    incomingCount = MAX_PINS;
  }

  bool slotLive[MAX_PINS] = {false};
  for (int i = 0; i < MAX_PINS; i++) {
    float v = (incoming != nullptr && i < incomingCount) ? incoming[i] : 0.0f;
    if (!sanitizeLevel01(&v)) {
      latestPinValues[i] = 0.0f;
      continue;
    }
    slotLive[i] = true;
    latestPinValues[i] = v;
  }
  hasLiveData = true;
  pushOutputs();
  ui_onPinFrame(latestPinValues, slotLive, incomingCount);
}

// =============================================================================
// WiFi (common)
// =============================================================================

static void startOscListening() {
  serialDebugPrintf("OSC listening on UDP port %d, path: %s\n", OSC_PORT, OSC_PATH);
  udp.begin(OSC_PORT);
}

static void initializeWiFi() {
  WiFi.mode(WIFI_STA);
  wm.setConfigPortalBlocking(false);
  wm.setConfigPortalTimeout(300);
  wm.setConnectTimeout(5);
  wm.setSaveConnectTimeout(10);

  if (wm.autoConnect("Red_Dust_Object")) {
    serialDebugPrintln("WiFi connected immediately");
    wifiConnected = true;
    startOscListening();
  } else {
    serialDebugPrintln("WiFi connection attempt started (non-blocking)");
    wifiConnected = false;
  }
}

static void updateWiFiStatus() {
  bool connected = (WiFi.status() == WL_CONNECTED);
  if (connected == wifiConnected) {
    return;
  }
  
  wifiConnected = connected;
  if (wifiConnected) {
    serialDebugPrintln("WiFi connected");
    startOscListening();
  } else {
    serialDebugPrintln("WiFi disconnected");
  }
}

// =============================================================================
// Init helpers (common)
// =============================================================================

static void initializeOutputs() {
#if ENABLE_I2S_PCM5102
  if (!i2s_audio_begin()) {
    serialDebugPrintln("WARNING: I2S/PCM5102 init failed — check wiring and pins in settings.h");
  }
#endif

#if ENABLE_TACTILE_OUTPUT
  if (!tactile_output_begin()) {
    serialDebugPrintln("WARNING: PWM tactile init failed — check PWM pins in settings.h");
  }
#endif
}

static void printBootBanner() {
  serialDebugPrintln("\nRed Dust Interactive Object (multi-pin)");
  serialDebugPrintln("Serial: v1[,v2,...],timestamp  (last comma = timestamp; up to MAX_PINS values)");
  serialDebugPrintln("OSC: base path + typetag ,f...fs + floats BE + timestamp string");
#if ENABLE_I2S_PCM5102
  serialDebugPrintf(
      "I2S -> PCM5102 shake: Pin_A=L Pin_B=R, OSC 0..1 -> volume + %.0f..%.0f Hz (C–F unused)\n",
      (double)I2S_CARRIER_HZ_MIN, (double)I2S_CARRIER_HZ_MAX);
#endif

#if ENABLE_TACTILE_OUTPUT
  serialDebugPrintf("Tactile: PWM GPIOs + %.0f Hz carrier (see settings.h)\n",
                    (double)PWM_TACTILE_CARRIER_HZ);
#endif

#if ENABLE_I2S_PCM5102 || ENABLE_TACTILE_OUTPUT
  serialDebugPrintln("Serial: FREQ,<Hz> forces fixed carrier (whiteboard)");
#endif
  serialDebugPrintln("==========================================");
}

// =============================================================================
// Arduino entry
// =============================================================================

void setup() {
  Serial.begin(SERIAL_BAUDRATE);
  delay(500);
  printBootBanner();

#if ACTIVE_BOARD == BOARD_ESP32_S3_DEVKITC_1
  ui_statusLedBootTest();
#endif

  ui_begin();
  initializeWiFi();

  input_begin();
  input_setCallbacks(applyPinFrame, setShakeCarrierHz);
  clearLivePinValues();
  initializeOutputs();

#if ACTIVE_BOARD == BOARD_ESP32_S3_DEVKITC_1
  // WiFi/I2S init can blank the WS2812; set idle red after peripherals are up.
  ui_statusLedInvalidate();
  ui_statusLedShowIdle();
#endif
}

void loop() {
  input_processSerial();

  silenceOutputsOnStreamIdle();
  
  wm.process();
  
  updateWiFiStatus();
  
  if (wifiConnected) {
    input_processOsc(udp);
  }
  
  ui_update(latestPinValues, input_streamActive());
#if ACTIVE_BOARD == BOARD_ESP32_S3_DEVKITC_1
  ui_statusLedUpdate(input_streamActive(), latestPinValues[0]);
#endif
  
delay(1);
}

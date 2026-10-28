#include "dy_hv20t.h"
#include "settings.h"

#if ENABLE_DY_HV20T

#include <HardwareSerial.h>

static HardwareSerial dySerial(DY_UART_NUM);

static const uint8_t CMD_PLAY[] = {0xAA, 0x02, 0x00, 0xAC};
static const uint8_t CMD_STOP[] = {0xAA, 0x04, 0x00, 0xAE};

static bool playing = false;
static bool stablePlay = HIGH;
static bool stableStop = HIGH;
static unsigned long playDebounceAt = 0;
static unsigned long stopDebounceAt = 0;

static void sendCmd(const uint8_t* cmd, size_t len) {
  dySerial.write(cmd, len);
  dySerial.flush();
}

bool dy_hv20t_begin() {
  pinMode(DY_PIN_PLAY_BTN, INPUT_PULLUP);
  pinMode(DY_PIN_STOP_BTN, INPUT_PULLUP);
  stablePlay = digitalRead(DY_PIN_PLAY_BTN);
  stableStop = digitalRead(DY_PIN_STOP_BTN);

  dySerial.begin(DY_BAUD, SERIAL_8N1, DY_RX_PIN, DY_TX_PIN);

  Serial.printf("DY-HV20T UART%d TX=GPIO%d baud=%d (IO1/RXD)\n", DY_UART_NUM, DY_TX_PIN,
                DY_BAUD);
  Serial.printf("DY buttons: Play=GPIO%d Stop=GPIO%d (momentary to GND)\n", DY_PIN_PLAY_BTN,
                DY_PIN_STOP_BTN);

#if DY_SEND_STOP_ON_BOOT
  delay(100);
  dy_hv20t_stop();
#endif
  delay(50);
  dy_hv20t_set_volume(DY_VOLUME);
  return true;
}

void dy_hv20t_set_volume(uint8_t volume) {
  if (volume > 30) volume = 30;
  uint8_t cmd[5] = {0xAA, 0x13, 0x01, volume, 0};
  cmd[4] = (uint8_t)((0xAA + 0x13 + 0x01 + volume) & 0xFF);
  sendCmd(cmd, sizeof(cmd));
  Serial.printf("DY CMD VOL %u  AA 13 01 %02X %02X\n", volume, volume, cmd[4]);
}

void dy_hv20t_play() {
  sendCmd(CMD_PLAY, sizeof(CMD_PLAY));
  playing = true;
  Serial.println(F("DY CMD PLAY  AA 02 00 AC"));
  dy_hv20t_set_volume(DY_VOLUME);
}

void dy_hv20t_stop() {
  sendCmd(CMD_STOP, sizeof(CMD_STOP));
  playing = false;
  Serial.println(F("DY CMD STOP  AA 04 00 AE"));
}

bool dy_hv20t_is_playing() { return playing; }

void dy_hv20t_update() {
  const unsigned long now = millis();

  const bool playLevel = digitalRead(DY_PIN_PLAY_BTN);
  if (playLevel != stablePlay) {
    if (playDebounceAt == 0) playDebounceAt = now;
    if ((now - playDebounceAt) >= DY_BTN_DEBOUNCE_MS) {
      if (stablePlay == HIGH && playLevel == LOW) {
        dy_hv20t_play();
        Serial.println(F("DY,BTN,PLAY"));
      }
      stablePlay = playLevel;
      playDebounceAt = 0;
    }
  } else {
    playDebounceAt = 0;
  }

  const bool stopLevel = digitalRead(DY_PIN_STOP_BTN);
  if (stopLevel != stableStop) {
    if (stopDebounceAt == 0) stopDebounceAt = now;
    if ((now - stopDebounceAt) >= DY_BTN_DEBOUNCE_MS) {
      if (stableStop == HIGH && stopLevel == LOW) {
        dy_hv20t_stop();
        Serial.println(F("DY,BTN,STOP"));
      }
      stableStop = stopLevel;
      stopDebounceAt = 0;
    }
  } else {
    stopDebounceAt = 0;
  }
}

#else  // !ENABLE_DY_HV20T

bool dy_hv20t_begin() { return false; }
void dy_hv20t_update() {}
void dy_hv20t_play() {}
void dy_hv20t_stop() {}
void dy_hv20t_set_volume(uint8_t /*volume*/) {}
bool dy_hv20t_is_playing() { return false; }

#endif

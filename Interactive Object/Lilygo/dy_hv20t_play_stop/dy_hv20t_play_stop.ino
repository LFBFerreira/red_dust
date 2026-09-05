#include "settings.h"

#include <HardwareSerial.h>

HardwareSerial dySerial(DY_UART_NUM);

static const uint8_t CMD_PLAY[] = {0xAA, 0x02, 0x00, 0xAC};
static const uint8_t CMD_STOP[] = {0xAA, 0x04, 0x00, 0xAE};

enum PlayState { STATE_STOPPED, STATE_PLAYING };
PlayState playState = STATE_STOPPED;

bool stablePlay = HIGH;
bool stableStop = HIGH;
unsigned long playDebounceAt = 0;
unsigned long stopDebounceAt = 0;

#if ENABLE_DISPLAY
#include <TFT_eSPI.h>
TFT_eSPI tft = TFT_eSPI();
PlayState lastDrawnState = (PlayState)255;
#endif

void sendCmd(const uint8_t *cmd, size_t len) {
  dySerial.write(cmd, len);
  dySerial.flush();
}

void setPlaying(bool playing) {
  if (playing) {
    sendCmd(CMD_PLAY, sizeof(CMD_PLAY));
    playState = STATE_PLAYING;
    Serial.println(F("CMD PLAY  AA 02 00 AC"));
  } else {
    sendCmd(CMD_STOP, sizeof(CMD_STOP));
    playState = STATE_STOPPED;
    Serial.println(F("CMD STOP  AA 04 00 AE"));
  }
}

#if ENABLE_DISPLAY
void drawStatus() {
  if (playState == lastDrawnState) return;
  lastDrawnState = playState;

  const uint16_t bg = playState == STATE_PLAYING ? TFT_DARKGREEN : TFT_MAROON;
  const char *label = playState == STATE_PLAYING ? "PLAYING" : "STOPPED";

  tft.fillScreen(bg);
  tft.setTextDatum(MC_DATUM);
  tft.setTextColor(TFT_WHITE, bg);
  tft.drawString("DY-HV20T", tft.width() / 2, tft.height() / 2 - 28, 4);
  tft.drawString(label, tft.width() / 2, tft.height() / 2 + 8, 4);
  tft.setTextDatum(BC_DATUM);
  tft.drawString("Play GPIO21  Stop GPIO22", tft.width() / 2, tft.height() - 8, 2);
}
#endif

void setup() {
  Serial.begin(115200);
  delay(200);
  Serial.println();
  Serial.println(F("DY-HV20T Play/Stop (UART Mode)"));
  Serial.printf("Play btn GPIO%d  Stop btn GPIO%d\n", PIN_PLAY_BTN, PIN_STOP_BTN);
  Serial.printf("UART%d TX=GPIO%d baud=%d -> DY IO1/RXD\n", DY_UART_NUM, DY_TX_PIN,
                DY_BAUD);

  pinMode(PIN_PLAY_BTN, INPUT_PULLUP);
  pinMode(PIN_STOP_BTN, INPUT_PULLUP);
  stablePlay = digitalRead(PIN_PLAY_BTN);
  stableStop = digitalRead(PIN_STOP_BTN);

  dySerial.begin(DY_BAUD, SERIAL_8N1, DY_RX_PIN, DY_TX_PIN);

#if ENABLE_DISPLAY
  pinMode(TFT_BL_PIN, OUTPUT);
  digitalWrite(TFT_BL_PIN, HIGH);
  tft.init();
  tft.setRotation(1);
  drawStatus();
#endif

#if SEND_STOP_ON_BOOT
  delay(100);
  setPlaying(false);
#endif

  Serial.println(F("Ready. Press Play / Stop."));
}

void loop() {
  const unsigned long now = millis();

  const bool playLevel = digitalRead(PIN_PLAY_BTN);
  if (playLevel != stablePlay) {
    if (playDebounceAt == 0) playDebounceAt = now;
    if ((now - playDebounceAt) >= BTN_DEBOUNCE_MS) {
      if (stablePlay == HIGH && playLevel == LOW) {
        setPlaying(true);
      }
      stablePlay = playLevel;
      playDebounceAt = 0;
    }
  } else {
    playDebounceAt = 0;
  }

  const bool stopLevel = digitalRead(PIN_STOP_BTN);
  if (stopLevel != stableStop) {
    if (stopDebounceAt == 0) stopDebounceAt = now;
    if ((now - stopDebounceAt) >= BTN_DEBOUNCE_MS) {
      if (stableStop == HIGH && stopLevel == LOW) {
        setPlaying(false);
      }
      stableStop = stopLevel;
      stopDebounceAt = 0;
    }
  } else {
    stopDebounceAt = 0;
  }

#if ENABLE_DISPLAY
  drawStatus();
#endif
}

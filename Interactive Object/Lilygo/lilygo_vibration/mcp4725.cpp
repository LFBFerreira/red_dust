#include "mcp4725.h"
#include "settings.h"

#if ENABLE_MCP4725

#include <Wire.h>

static bool s_ready = false;

bool mcp4725_begin() {
  Wire.begin(I2C_SDA_PIN, I2C_SCL_PIN);
  Wire.setClock(400000);

  bool ok = true;
  for (int i = 0; i < MCP4725_COUNT; i++) {
    Wire.beginTransmission(MCP4725_I2C_ADDR[i]);
    if (Wire.endTransmission() != 0) {
      Serial.printf("MCP4725[%d] not found at 0x%02X\n", i, MCP4725_I2C_ADDR[i]);
      ok = false;
    } else {
      Serial.printf("MCP4725[%d] OK at 0x%02X (Pin_%c tactile)\n", i, MCP4725_I2C_ADDR[i],
                    'A' + i);
    }
  }

  s_ready = ok;
  return ok;
}

void mcp4725_write(uint8_t deviceIndex, uint16_t value12) {
  if (!s_ready || deviceIndex >= MCP4725_COUNT) {
    return;
  }

  if (value12 > 4095) {
    value12 = 4095;
  }

  uint8_t addr = MCP4725_I2C_ADDR[deviceIndex];
  // Fast write: C2 C1 PD1 PD0 D11..D0 (power-down 0, no EEPROM)
  uint8_t b0 = (value12 >> 8) & 0x0F;
  uint8_t b1 = value12 & 0xFF;

  Wire.beginTransmission(addr);
  Wire.write(b0);
  Wire.write(b1);
  Wire.endTransmission();
}

void mcp4725_write_level(uint8_t deviceIndex, float level01) {
  if (level01 < 0.0f) level01 = 0.0f;
  if (level01 > 1.0f) level01 = 1.0f;
  uint16_t v = (uint16_t)(level01 * 4095.0f + 0.5f);
  mcp4725_write(deviceIndex, v);
}

#endif  // ENABLE_MCP4725

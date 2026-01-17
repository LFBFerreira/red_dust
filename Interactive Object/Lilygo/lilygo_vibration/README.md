# LilyGO Vibration Motor Controller

## Quick Start

### 1. Install Required Libraries

#### Install TFT_eSPI Library

**Option A: Using Arduino Library Manager (Recommended)**
1. Open Arduino IDE
2. Go to **Sketch → Include Library → Manage Libraries...**
3. Search for **"TFT_eSPI"** by Bodmer
4. Click **Install** (or **Update** if already installed)

**Option B: Manual Installation**
1. Download the latest version from: https://github.com/Bodmer/TFT_eSPI
2. Extract the ZIP file
3. Rename the folder to `TFT_eSPI` (if not already)
4. Copy the folder to: `C:\Users\<Your User Name>\Documents\Arduino\libraries\`

#### Install TFT_eWidget Library (Optional, for GUI widgets)

**Option A: Using Arduino Library Manager**
1. In Arduino IDE, go to **Sketch → Include Library → Manage Libraries...**
2. Search for **"TFT_eWidget"** by Bodmer
3. Click **Install** (or **Update** if already installed)

**Option B: Manual Installation**
1. Download from: https://github.com/Bodmer/TFT_eWidget
2. Extract and copy to: `C:\Users\<Your User Name>\Documents\Arduino\libraries\TFT_eWidget`

### 2. Configure TFT_eSPI for TTGO T-Display

**Important:** You must configure TFT_eSPI to use the correct setup file for your TTGO T-Display.

1. Navigate to: `C:\Users\<Your User Name>\Documents\Arduino\libraries\TFT_eSPI\`
2. Open `User_Setup_Select.h` in a text editor (Notepad, VS Code, etc.)
3. Find these lines (around line 27-58):
   ```cpp
   //#include <User_Setup.h>           // Default setup is root library folder
   ...
   //#include <User_Setups/Setup25_TTGO_T_Display.h>    // Setup file for ESP32 and TTGO T-Display
   ```
4. **Comment out** the default setup (add `//` if not already commented):
   ```cpp
   //#include <User_Setup.h>           // Default setup is root library folder
   ```
5. **Uncomment** the TTGO T-Display setup (remove `//`):
   ```cpp
   #include <User_Setups/Setup25_TTGO_T_Display.h>    // Setup file for ESP32 and TTGO T-Display ST7789V SPI bus TFT
   ```
6. Save the file

**Note:** Only ONE setup file should be uncommented at a time.

### 3. Configure Arduino IDE Board Settings

**Recommended: Use the LilyGo T-Display Board Definition**

Arduino IDE includes a specific board definition for the LilyGo T-Display, which has the correct settings pre-configured.

**Note:** If you don't see the ESP32 board options, you need to install ESP32 board support:
1. Go to **File → Preferences**
2. In "Additional Boards Manager URLs", add: `https://raw.githubusercontent.com/espressif/arduino-esp32/gh-pages/package_esp32_index.json`
3. Go to **Tools → Board → Boards Manager...**
4. Search for "ESP32" and install "esp32" by Espressif Systems
5. Restart Arduino IDE

**Select the Board:**
1. Open Arduino IDE
2. Go to **Tools → Board → ESP32 Arduino → LilyGo T-Display**
3. The board settings should be automatically configured, but verify:
   - **PSRAM:** Disable (should be default)
   - **Flash Size:** 4MB (32Mb) (should be default)
   - **Partition Scheme:** Default (or as needed)
   - **CPU Frequency:** 240MHz (WiFi/BT) (should be default)
   - **Upload Speed:** 921600 (or lower if you have upload issues)
   - **Core Debug Level:** None (or as needed)
4. Select the correct **Port** (COM port) under **Tools → Port**

**Alternative: If LilyGo T-Display board is not available:**
- Use **Tools → Board → ESP32 Arduino → ESP32 Dev Module**
- Manually configure the settings listed above

### 4. Test the Display

1. Open an example sketch:
   - Go to **File → Examples → TFT_eSPI → 320 x 240 → FactoryTest**
   - Or any other example from the TFT_eSPI library
2. **Verify/Compile** the sketch (checkmark icon)
3. **Upload** the sketch (right arrow icon)
4. The display should show the factory test pattern

**If the display is blank:**
- Check that the backlight is enabled in your code:
  ```cpp
  pinMode(4, OUTPUT);
  digitalWrite(4, HIGH);  // Turn on backlight (pin 4 for TTGO T-Display)
  ```

### 5. Upload Your Project

1. Open your project sketch (`lilygo_vibration.ino`)
2. Verify the code compiles without errors
3. Upload to your board
4. Open Serial Monitor (115200 baud) to see debug messages

## How It Works

This project controls a vibration motor based on data received from a computer or another device. Think of it like a volume control for vibration - when you send a number between 0 and 1 (where 0 means no vibration and 1 means maximum vibration), the device converts that number into a vibration intensity. 

The device listens for messages sent over the USB connection in a simple format: a number followed by a timestamp. When it receives a message, it immediately adjusts the vibration motor's strength to match that number. For example, if you send 0.5, the motor will vibrate at half intensity. If you send 0, it stops vibrating completely. The device continuously updates the vibration in real-time as new messages arrive, creating a responsive haptic feedback system.

## Troubleshooting

### Compilation Errors

**Error: 'GPIO' was not declared in this scope**
- This occurs with newer ESP32 cores (3.x). The TFT_eSPI library should be updated to the latest version (2.5.43+).
- If the error persists, check that `hal/gpio_ll.h` is included in `Processors/TFT_eSPI_ESP32.h`

**Error: Multiple libraries found**
- Make sure you only have one copy of TFT_eSPI in your libraries folder
- Remove any duplicate installations

### Display Issues

**Display is blank/not working:**
- Verify `User_Setup_Select.h` is configured correctly (Setup25 uncommented)
- Check that backlight pin (GPIO 4) is enabled in your code
- Verify all connections are secure
- Try reducing SPI frequency in `Setup25_TTGO_T_Display.h` if needed

**Display shows garbled output:**
- Check that the correct driver is selected (ST7789 for TTGO T-Display)
- Verify pin assignments match your hardware
- Try a different example sketch to isolate the issue

## Resources

- **TFT_eSPI Library:** https://github.com/Bodmer/TFT_eSPI
- **TFT_eWidget Library:** https://github.com/Bodmer/TFT_eWidget
- **TTGO T-Display Info:** https://github.com/Xinyuan-LilyGO/TTGO-T-Display
- **ESP32 Arduino Core:** https://github.com/espressif/arduino-esp32

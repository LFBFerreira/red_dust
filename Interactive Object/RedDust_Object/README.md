# Red Dust Object - ESP32-S3 RGB LED Controller

An ESP32-S3 project that controls an RGB LED based on Serial or OSC (Open Sound Control) messages. The LED displays colors from red to blue based on normalized values (0.0 to 1.0).

## Hardware Requirements

- ESP32-S3-DevKitC-1 board
- WS2812B RGB LED (connected to GPIO 38, or GPIO 48 for v1.0 boards)

## Setup Instructions

### Option 1: Using PlatformIO with VSCode or Cursor

1. **Install PlatformIO**
   - Open VSCode or Cursor
   - Install the "PlatformIO IDE" extension from the marketplace
   - Restart the editor

2. **Open the Project**
   - Open this project folder in VSCode/Cursor
   - PlatformIO will automatically detect the `platformio.ini` configuration

3. **Connect Your Board**
   - Connect your ESP32-S3-DevKitC-1 to your computer via USB
   - PlatformIO should automatically detect the port

4. **Build and Upload**
   - Click the checkmark icon (✓) in the PlatformIO toolbar to build
   - Click the arrow icon (→) to upload to your board
   - The serial monitor will open automatically at 115200 baud

5. **Configure WiFi** (if needed)
   - The board will attempt to connect to WiFi automatically
   - If connection fails, check the serial monitor for the AP mode details
   - Connect to the "RedDust_Object" access point to configure WiFi

### Option 2: Using Arduino IDE

1. **Install ESP32 Board Support**
   - Open Arduino IDE
   - Go to **File → Preferences**
   - Add this URL to "Additional Board Manager URLs":
     ```
     https://raw.githubusercontent.com/espressif/arduino-esp32/gh-pages/package_esp32_index.json
     ```
   - Go to **Tools → Board → Boards Manager**
   - Search for "ESP32" and install "esp32 by Espressif Systems"
   - Select **Tools → Board → ESP32 Arduino → ESP32S3 Dev Module**

2. **Install Required Libraries**
   - Go to **Sketch → Include Library → Manage Libraries**
   - Install these libraries:
     - **FastLED** by Daniel Garcia (version 3.6.0 or newer)
     - **OSC** by CNMAT (version 1.0.0 or newer)
     - **WiFiManager** by tzapu (version 2.0.17 or newer)

3. **Prepare the Sketch**
   - Create a new sketch folder in your Arduino sketches directory
   - Copy all files from the `src` folder into your sketch folder:
     - `main.cpp` (rename to `main.ino`)
     - `network.cpp`
     - `network.h`

4. **Configure the Board**
   - Select **Tools → Board → ESP32S3 Dev Module**
   - Select the correct **Port** (Tools → Port)
   - Set **Upload Speed** to 921600 (or lower if you have issues)
   - Set **CPU Frequency** to 240MHz
   - Set **Flash Size** to match your board
   - Set **Partition Scheme** to "Default 4MB with spiffs"

5. **Upload the Code**
   - Click the Upload button (→) in Arduino IDE
   - Wait for the upload to complete

6. **Open Serial Monitor**
   - Go to **Tools → Serial Monitor**
   - Set baud rate to **115200**
   - You should see connection status messages

7. **Configure WiFi** (if needed)
   - If WiFi connection fails, the board will create an access point
   - Connect to "RedDust_Object" WiFi network
   - Open a browser and go to the configuration portal
   - Enter your WiFi credentials

## WiFi Configuration

To change the WiFi credentials in the code, edit the `src/network.cpp` file:

1. Open `src/network.cpp`
2. Find these lines (around line 6-7):
   ```cpp
   const char* wifiSSID = "WIFI NAME";
   const char* wifiPassword = "WIFI PASS";
   ```
3. Replace `"IBelieveICanWifi"` with your WiFi network name (SSID)
4. Replace `"Sayplease2times"` with your WiFi password
5. Save the file and rebuild/upload the code to your board

**Note**: After changing the credentials, you'll need to rebuild and upload the code again for the changes to take effect.

## Usage

### Serial Communication
Send normalized values (0.0 to 1.0) via Serial in the format:
```
value,timestamp
```
Example: `0.5,1234567890`

- 0.0 = Red
- 1.0 = Blue
- Values in between = gradient from red to blue

### OSC Communication
Send OSC messages to the board's IP address on port 8000:
- Address: `/red_dust/object_1`
- Value: Float between 0.0 and 1.0

## LED Status Indicators

- **Red**: Neither Serial nor WiFi connected
- **Black**: Connected but no data received yet
- **Color (Red to Blue)**: Receiving data and displaying color based on value

## Troubleshooting

- **LED not working**: Check if your board uses GPIO 38 or GPIO 48 (see `main.cpp` line 11)
- **WiFi not connecting**: Check serial monitor for error messages and use AP mode to reconfigure
- **Upload fails**: Try lowering the upload speed or pressing the BOOT button during upload
- **Libraries not found**: Make sure all required libraries are installed in Arduino IDE

## Project Structure

```
RedDust_Object/
├── src/
│   ├── main.cpp      # Main program logic
│   ├── network.cpp   # WiFi and network handling
│   └── network.h     # Network function declarations
├── platformio.ini    # PlatformIO configuration
└── README.md         # This file
```

# LilyGO Vibration Motor Controller

## Quick Start

1. Copy **TFT_eSPI** to the `<C:\Users\Your User Name\Documents\Arduino\libraries>` directory
2. Open **Arduino IDE**, find **TFT_eSPI** in the file, and for example, the T-Display factory test program is located at **TFT_eSPI -> FactoryTest**, you can also use other sample programs provided by TFT_eSPI
3. In the **Arduino IDE** tool options, select the development board **ESP32 Dev Module**, select **Disable** in the PSRAM option, select **4MB** in the Flash Size option, Other keep the default
4. Select the corresponding serial port. If you are not sure, please remove all the serial ports, leaving the board in the USB connection state, just select that one
5. Finally, click upload, the right arrow next to the tick

## How It Works

This project controls a vibration motor based on data received from a computer or another device. Think of it like a volume control for vibration - when you send a number between 0 and 1 (where 0 means no vibration and 1 means maximum vibration), the device converts that number into a vibration intensity. 

The device listens for messages sent over the USB connection in a simple format: a number followed by a timestamp. When it receives a message, it immediately adjusts the vibration motor's strength to match that number. For example, if you send 0.5, the motor will vibrate at half intensity. If you send 0, it stops vibrating completely. The device continuously updates the vibration in real-time as new messages arrive, creating a responsive haptic feedback system.

## Resources

The TFT_eSPI library mentioned above can be found at: https://github.com/Xinyuan-LilyGO/TTGO-T-Display

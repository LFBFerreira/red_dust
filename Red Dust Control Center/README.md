# Red Dust Control Center

A desktop application for controlling the Becoming Red Dust installation. Transforms real seismic data from Mars into sound, light, and physical movement through OSC streaming.

## Features

- Load continuous waveform data from NASA's InSight SEIS archive
- Visualize multi-channel seismic waveforms
- Time-based playback with adjustable speed and looping
- Stream normalized data via OSC at 60 Hz to multiple interactive objects
- Per-object scaling and configuration
- Session save/load functionality

## Requirements

- Python 3.8 or higher
- See `requirements_windows.txt` or `requirements_mac.txt` for platform-specific dependencies

## Installation

### Windows
```bash
pip install -r requirements_windows.txt
```

### macOS
```bash
pip install -r requirements_mac.txt
```

## Usage

Run the application:
```bash
python main.py
```

## Understanding the Waveform Display

### Amplitude Units: "Counts"

The waveform viewer displays amplitude values, and the unit shown depends on the data:

- **"Counts"**: This is the default unit shown when the seismic data is uncalibrated. "Counts" refers to the raw digital values from the seismometer's analog-to-digital converter (ADC) - these are integer values before calibration to physical units.

- **Physical Units**: If the data is calibrated, channels may display physical units such as:
  - Velocity (m/s)
  - Acceleration (m/s²)
  - Displacement (nm, m)
  
The amplitude label updates based on the active channel's metadata. If a channel has unit information in its ObsPy trace stats, that unit will be displayed. Otherwise, it defaults to "Counts".

**Note**: Different channels may have different units if some are calibrated and others are not. The label reflects the unit of the currently active channel.

## Project Structure

- `core/` - Core logic (data management, playback, OSC streaming)
- `ui/` - User interface components
- `cache/` - Local data cache (mirrors PDS structure)
- `sessions/` - Saved session files

## Data Sources

Data is fetched from NASA's Planetary Data System (PDS) InSight SEIS archive:
https://pds-geosciences.wustl.edu/insight/urn-nasa-pds-insight_seis/data/

## License

[To be determined]


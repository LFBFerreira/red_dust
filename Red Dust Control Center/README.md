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


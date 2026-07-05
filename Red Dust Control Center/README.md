# Red Dust Control Center

Application source for the Red Dust Control Center desktop app.

**Installation and launch scripts** are documented in the [repository README](../README.md).

## Project structure

- `core/` — Data management, playback, OSC and serial streaming
- `ui/` — User interface
- `cache/` — Local data cache (mirrors PDS structure; created at runtime)
- `sessions/` — Saved session files (created at runtime)

## Data sources

NASA PDS InSight SEIS archive: https://pds-geosciences.wustl.edu/insight/urn-nasa-pds-insight_seis/data/

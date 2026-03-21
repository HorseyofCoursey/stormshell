StormShell ☼

A Python curses weather display for Raspberry Pi. Runs in an SSH terminal or as a full-screen HDMI kiosk with no desktop required. All ASCII art, no dependencies beyond the Python standard library.

![Python](https://img.shields.io/badge/python-3.9%2B-blue) ![Platform](https://img.shields.io/badge/platform-Raspberry%20Pi-red) ![License](https://img.shields.io/badge/license-MIT-green)

---

## Features

- **Live weather** — temperature, feels like, humidity, wind, and a 4-hour forecast
- **Weather animations** — hand-drawn ASCII art for sun, clouds, rain, snow, fog, storms and more
- **Analog clock** — ASCII art clock face with hour, minute, and second hands
- **Digital clock** — full-screen big-digit display
- **Moon phase** — calculated locally, no API needed
- **Sunrise & sunset** times
- **AQI bar** — color-coded air quality index
- **Pressure gauge** — trend needle showing rising, steady, or falling
- **Auto units** — Celsius/Fahrenheit and km/h/mph based on resolved location country
- **Global locations** — city names, ZIP codes, or postal codes; non-Latin city names automatically anglicized for TTY display

---

## Hardware

Designed for **Raspberry Pi Zero 2W** but works on any Pi running Raspberry Pi OS Lite.

- HDMI output via mini-HDMI adapter
- Uni Terminus Bold 28×14 font at 1080p → 97×27 terminal
- Also works over SSH in any terminal window

---

## Installation

```bash
git clone https://github.com/HorseyofCoursey/stormshell.git
cd stormshell
chmod +x install.sh
sudo ./install.sh
```

The installer will ask for your location and installs a `stormshell` command system-wide.

---

## Usage

```bash
# Basic usage
stormshell --location "Chicago"
stormshell --location "60602"
stormshell --location "London" --country gb
stormshell --location "SW1A 1AA"

# HDMI kiosk mode (outputs to TTY1)
stormshell --display --location "Calumet City"

# Force units
stormshell --location "New York" --units celsius --wind kmh

### Keys

| Key | Action |
|-----|--------|
| `a` | Toggle full-screen analog clock |
| `d` | Toggle full-screen digital clock |
| `r` | Force weather refresh |
| `q` / `Esc` | Quit |

---

## Data Sources

| Source | Used for |
|--------|----------|
| [Open-Meteo](https://open-meteo.com) | Weather forecast, pressure, sunrise/sunset |
| [Open-Meteo Air Quality](https://open-meteo.com/en/docs/air-quality-api) | AQI / PM2.5 |
| [Nominatim / OSM](https://nominatim.openstreetmap.org) | Location lookup |
| Math | Moon phase (no API) |

No API keys required.

---

## Running as a Service

The installer sets up a systemd service for automatic startup:

```bash
sudo systemctl enable stormshell
sudo systemctl start stormshell
sudo systemctl stop stormshell
```

---

## Weather Conditions

`sunny` · `partly_cloudy` · `cloudy` · `drizzle` · `rain` · `showers` · `heavy_rain` · `snow` · `blizzard` · `storm` · `fog`

---

## License

MIT

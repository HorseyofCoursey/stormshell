# StormShell ☼

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
- **Auto units** — Celsius/Fahrenheit and km/h/mph detected automatically from location
- **Global locations** — city names, ZIP codes, or postal codes worldwide

---

## Hardware

Will work on any Pi hardware on both Raspberry Pi OS Lite and the full desktop image. On desktop, just open a terminal and run stormshell --location "London". The --display kiosk mode is intended for headless/Lite setups..

- HDMI output via mini-HDMI adapter
- Works over SSH in any terminal window

---

## Installation

```bash
curl -sSL https://raw.githubusercontent.com/HorseyofCoursey/stormshell/main/install.sh | sudo bash
```

---

## Usage

```bash
# City names
stormshell --location "London"
stormshell --location "Tokyo"
stormshell --location "New York"
stormshell --location "Paris"
stormshell --location "Sydney"
stormshell --location "Berlin"

# US ZIP codes
stormshell --location "10001"
stormshell --location "90210"

# UK postcodes
stormshell --location "SW1A 1AA"
stormshell --location "M1 1AE"

# Canadian postcodes
stormshell --location "M5V 3L9"

# Ambiguous names — add a country code to be specific
stormshell --location "Springfield" --country us
stormshell --location "Richmond" --country gb
stormshell --location "Perth" --country au

# HDMI kiosk mode (outputs to TTY1)
stormshell --display --location "London"

# Override units (auto-detected by default)
stormshell --location "London" --units fahrenheit --wind mph

# Preview all weather animations
stormshell --preview

# Preview a specific condition
stormshell --preview --condition storm
```

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

## Weather Conditions

`sunny` · `partly_cloudy` · `cloudy` · `drizzle` · `rain` · `showers` · `heavy_rain` · `snow` · `blizzard` · `storm` · `fog`

---

## License

MIT

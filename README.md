# StormShell ☼

A Python curses weather display. Runs in any terminal over SSH or as a full-screen HDMI kiosk on Raspberry Pi. All ASCII art, no dependencies beyond the Python standard library.

![Python](https://img.shields.io/badge/python-3.9%2B-blue) ![Platform](https://img.shields.io/badge/platform-Linux%20%7C%20macOS-lightgrey) ![License](https://img.shields.io/badge/license-MIT-green)

---

## Features

- **Live weather** — temperature, feels like, humidity, wind, and a 4-hour forecast
- **Weather animations** — hand-drawn ASCII art for sun, clouds, rain, snow, fog, storms and more
- **Night mode** — automatically switches to star field + moon phase animation after sunset
- **Analog clock** — ASCII art clock face with hour, minute, and second hands
- **Digital clock** — full-screen big-digit display
- **Moon phase** — calculated locally, no API needed
- **Sunrise & sunset** times
- **AQI bar** — color-coded air quality index
- **Pollen count** — dominant type and severity (where available)
- **Pressure gauge** — trend needle showing rising, steady, or falling
- **Auto units** — Celsius/Fahrenheit and km/h/mph detected automatically from location
- **Global locations** — city names, ZIP codes, or postal codes worldwide

---

## Works on any Linux or macOS terminal

StormShell runs wherever Python 3.9+ is available. Open a terminal and run it over SSH, in a desktop terminal emulator, or directly on a console.

> **Note:** `--kiosk` mode (full-screen HDMI output) is Raspberry Pi specific — it uses Linux TTY tools to take over the HDMI display without a desktop environment.

---

## Terminal Size

Designed for **97×27 minimum**. This is what you get with Terminus Bold 28×14 at 1080p on a Pi's TTY. Larger terminals work but the layout is optimised for this size.

For SSH, resize your terminal before running:
```bash
printf '\e[8;27;97t'
```

---

## Installation

```bash
curl -sSL https://raw.githubusercontent.com/HorseyofCoursey/stormshell/main/install.sh | sudo bash
```

Or clone manually:
```bash
git clone https://github.com/HorseyofCoursey/stormshell.git
cd stormshell && sudo ./install.sh
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

# Kiosk mode — Raspberry Pi only, outputs to HDMI TTY1
stormshell --kiosk --location "London"
stormshell --display --location "London"   # legacy alias, same thing

# Override units (auto-detected by default)
stormshell --location "London" --units fahrenheit --wind mph

# Preview all weather animations
stormshell --preview

# Preview a specific condition
stormshell --preview --condition storm
stormshell --preview --condition night
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
| [Open-Meteo Air Quality](https://open-meteo.com/en/docs/air-quality-api) | AQI / PM2.5 / pollen |
| [Nominatim / OSM](https://nominatim.openstreetmap.org) | Location lookup |
| Math | Moon phase (no API) |

No API keys required.

---

## Weather Conditions

`sunny` · `partly_cloudy` · `cloudy` · `drizzle` · `rain` · `showers` · `heavy_rain` · `snow` · `blizzard` · `storm` · `fog` · `night` · `night_partly_cloudy`

---

## License

MIT

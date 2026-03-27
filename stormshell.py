#!/usr/bin/env python3
"""
StormShell — animated StormShell for the terminal
──────────────────────────────────────────────────────────────
Single unified character set — works identically on:
  * SSH / any terminal emulator
  * HDMI kiosk via /dev/tty1  (load Uni Terminus font via setfont in service)

Characters used:
  Box drawing   - | + (ASCII) and box-draw: - | + for borders
  Block elems   : (ASCII compatible) . , | / \\ * ~ = #
  CP437 sun     : (fallback: *) -- see FONT NOTE below
  Pure ASCII    : everything else

FONT NOTE: The ☼ character (U+263C) is present in every Uni-family console
font (Terminus, LatArCyrHeb, etc.). The install script loads
Uni2-TerminusBold28x14 before the display starts on the TTY. On SSH the
terminal emulator handles it. If ☼ renders as '?' on your setup, flip
the SUN_CHAR constant below to '*'.

Data:   Open-Meteo (no key)    https://open-meteo.com
Coords: Nominatim/OSM (no key) https://nominatim.openstreetmap.org

Usage:
  python3 stormshell.py --zip 60201
  python3 stormshell.py --zip SW1A --country gb --units celsius --wind kmh
"""

import curses
import time
import json
import sys
import os
import signal
import atexit
import subprocess
import argparse
import urllib.request
import urllib.parse
from datetime import datetime

# ─── Config ───────────────────────────────────────────────────────────────────

DEFAULT_LOCATION = ""            # set by installer
DEFAULT_COUNTRY  = ""           # empty = let Nominatim search globally
REFRESH_SECONDS  = 300
ANIMATE_FPS      = 3
TEMP_UNIT        = "fahrenheit"   # fahrenheit | celsius
WIND_UNIT        = "mph"          # mph | kmh | ms | kn

# If ☼ shows as '?' on your TTY, change this to '*'
SUN_CHAR = "☼"

# Countries that default to metric units when --units/--wind not specified.
# If the resolved country code is in this set, celsius + kmh are used.
METRIC_COUNTRIES = {
    "gb", "au", "ca", "nz", "ie", "za",   # anglophone metric
    "de", "fr", "es", "it", "pt", "nl",   # western Europe
    "be", "ch", "at", "se", "no", "dk",   # more Europe
    "fi", "pl", "cz", "sk", "hu", "ro",
    "jp", "cn", "kr", "in", "br", "mx",   # major non-EU
    "ar", "cl", "co", "pe", "ng", "ke",
    "eg", "tr", "ru", "ua", "th", "vn",
    "id", "ph", "pk", "bd", "sg", "my",
}

# ─── WMO code → condition string ──────────────────────────────────────────────

def wmo_to_condition(code):
    if code == 0:                   return "sunny"
    if code in (1, 2):              return "partly_cloudy"
    if code == 3:                   return "cloudy"
    if code in (45, 48):            return "fog"
    if code in (51, 53, 55):        return "drizzle"
    if code in (61, 63):            return "rain"
    if code in (65,):               return "heavy_rain"
    if code in (80, 81):            return "showers"
    if code in (82,):               return "heavy_rain"
    if code in (71, 73, 85):        return "snow"
    if code in (75, 86):            return "blizzard"
    if code in (95, 96, 99):        return "storm"
    return "cloudy"

# 3-char forecast condition labels — pure ASCII, no emoji
CONDITION_LABEL = {
    "sunny":         "Clear Sky",
    "partly_cloudy": "Partly Cloudy",
    "cloudy":        "Overcast",
    "fog":           "Foggy",
    "drizzle":       "Drizzle",
    "rain":          "Rainy",
    "heavy_rain":    "Heavy Rain",
    "showers":       "Showers",
    "snow":          "Snowy",
    "blizzard":      "Blizzard",
    "storm":         "Thunderstorm",
}

FC_ICON = {
    "sunny":         "SUN",
    "partly_cloudy": "PCT",
    "cloudy":        "CLD",
    "fog":           "FOG",
    "drizzle":       "DRZ",
    "rain":          "RAN",
    "heavy_rain":    "HVY",
    "showers":       "SHW",
    "snow":          "SNW",
    "blizzard":      "BLZ",
    "storm":         "STM",
}

# ─── ASCII Art ────────────────────────────────────────────────────────────────
#
#  Full palette (works on SSH terminal and /dev/tty1 with Uni Terminus font):
#
#    ☼           CP437 WHITE SMILING FACE (U+263C) — sun symbol
#    \ / | ( )   pure ASCII geometry
#    . , ' ` ~   punctuation as texture
#    * #          fill / snow / stars
#    ░ ▒ ▓        block elements — fog, bars
#    - + =        horizontal lines
#
#  No emoji. No multi-codepoint sequences. No >8 colour pairs.
#
#  Each condition: list of animation frames.
#  Each frame:    list of exactly ART_H strings, each ART_W chars wide.

ART_W = 62   # matches right panel width at 97-col display (div_x=32, right_x=34, right_w=62)
ART_H = 40   # tall canvas — clipped to actual anim_h at draw time

def _p(s):
    """Clip to ART_W and left-pad so every line is the same width."""
    return s[:ART_W].ljust(ART_W)


# ── SUNNY ─────────────────────────────────────────────────────────────────────
# User's hand-drawn sun, centered, 2-frame twinkle on the rays.

def _sunny():
    # 9 rows tall — if canvas too short, top rows get cropped automatically
    SUN = [
        "      ;   :   ;      ",
        "   .   \\_,!,_/   ,   ",
        "    `.,'     `.,'    ",
        "     /         \\     ",
        " -- :   -0--0-  : -- ",
        "     \\   .__,  /     ",
        "    ,'`._   _.'`.    ",
        "   '   / `!` \\    `  ",
        "      ;   :   ;      ",
    ]
    SUN2 = [
        "                     ",
        "       \\_,!,_/       ",
        "    `.,'     `.,`    ",
        "     /         \\     ",
        "    -: -0--0 -  :-   ",
        "     \\  .__,   /     ",
        "    ,'`._   _,``.    ",
        "       / `!` \\       ",
        "                     ",
    ]
    def _frame(art):
        rows = []
        for line in art:
            rows.append(_p(line.center(ART_W)))
        # Trim to ART_H - 1 rows, place at top (row 1 to leave space for border)
        rows = rows[:ART_H - 1]
        # Pad bottom if art shorter than canvas
        while len(rows) < ART_H - 1:
            rows.append(_p(""))
        rows.append(_p("      CLEAR SKY      "))
        return rows

    f1 = _frame(SUN)
    f2 = _frame(SUN2)
    # Repeat each frame 4x → flicker every ~1.3s at 3fps
    return [f1, f1, f1, f1, f2, f2, f2, f2]


# ── PARTLY CLOUDY ─────────────────────────────────────────────────────────────
# User's sun with two clouds scrolling over it — drawn live in draw_frame
# so each cloud loops independently with no disappearing.

def _partly_cloudy():
    import random
    rng = random.Random(42)

    SUN = [
        "      ;   :   ;      ",
        "   .   \\_,!,_/   ,   ",
        "    `.,'     `.,'    ",
        "     /         \\     ",
        " -- :   -0--0-  : -- ",
        "     \\   .__,  /     ",
        "    ,'`._   _.'`.    ",
        "   '   / `!` \\    `  ",
        "      ;   :   ;      ",
    ]
    SUN2 = [
        "                     ",
        "       \\_,!,_/       ",
        "    `.,'     `.,`    ",
        "     /         \\     ",
        "    -: -0--0 -  :-   ",
        "     \\  .__,   /     ",
        "    ,'`._   _,``.    ",
        "       / `!` \\       ",
        "                     ",
    ]

    # Pre-render sun frames (flicker) — clouds drawn live in draw_frame
    frames = []
    for f in range(8):
        sun_art = SUN if (f // 4) % 2 == 0 else SUN2
        grid = [[' '] * ART_W for _ in range(ART_H)]
        for r, line in enumerate(sun_art):
            if r >= ART_H - 1: break
            for c, ch in enumerate(line):
                if 0 <= c < ART_W:
                    grid[r][c] = ch
        frame = [_p(''.join(row)) for row in grid]
        frame[ART_H - 1] = _p("   PARTLY CLOUDY   ")
        frames.append(frame)
    return frames


# ── CLOUDY ────────────────────────────────────────────────────────────────────
# Multiple hand-drawn clouds scroll left to right simultaneously.
# Staggered start positions give layered depth effect.

# All 5 user cloud shapes
_CLOUD_SHAPES = [
    [
        "             .....",
        "      ...   (     )",
        "     (   )-(       )",
        "  .-.'              )",
        " (                    )",
        "  `-------------------'",
    ],
    [
        "             .....     ___",
        "      ...   (     )   (   ).",
        "     (   )-(       )-(      )",
        "  .-.'                       ).-.  ",
        " (                               )",
        "  `-----------------------------'",
    ],
    [
        "          ........     ___",
        "      ...(        )   (   ).",
        "     (             )-(      )",
        "  .-.'                       ).-.  ",
        " (                               )",
        "  `-----------------------------'",
    ],
    [
        "          ...",
        "      ...(   )..",
        "     (          )...",
        "  .-.'              ).",
        " (                    )",
        "  `-------------------'",
    ],
    [
        "          ...                  .....",
        "      ...(   )..            ..(     )",
        "     (          )...    ...(         '...--.  ",
        "  .-.'              )--(                    ).-.",
        " (                                              )",
        "  `---------------------------------------------",
    ],
]

def _render_clouds(cloud_list, x_offset, label):
    """Render multiple clouds onto one frame at given x scroll offset.
    cloud_list: list of (shape_idx, x_start, y_start) tuples."""
    grid = [[' '] * ART_W for _ in range(ART_H)]

    for shape_idx, base_x, y_start in cloud_list:
        lines = _CLOUD_SHAPES[shape_idx]
        cloud_w = max(len(l.rstrip()) for l in lines)
        # current x = base_x + scroll offset, wraps around
        total = ART_W + cloud_w
        x = ((base_x + x_offset) % total) - cloud_w
        for row_i, line in enumerate(lines):
            r = y_start + row_i
            if r < 0 or r >= ART_H - 1:
                continue
            for col_i, ch in enumerate(line.rstrip()):
                col = x + col_i
                if 0 <= col < ART_W and ch != ' ':
                    grid[r][col] = ch

    frame = [_p(''.join(row)) for row in grid]
    frame[ART_H - 1] = _p(label)
    return frame


def _cloudy():
    import random
    rng = random.Random(7)

    # (shape_idx, x_phase, y_row, speed)
    # y can be negative or past bottom for natural cropping
    clouds = [
        (1,  0,  rng.randint(-2, 1), 1),
        (3,  28, rng.randint(0,  5), 4),
        (0,  52, rng.randint(-1, 3), 1),
        (4,  12, rng.randint(2,  6), 5),
        (2,  72, rng.randint(-2, 2), 2),
    ]

    total = ART_W + 67   # +7 to clear right edge fully
    frames = []
    for f in range(total):
        grid = [[' '] * ART_W for _ in range(ART_H)]
        for shape_idx, base_x, y_start, speed in clouds:
            lines = _CLOUD_SHAPES[shape_idx]
            cw    = max(len(l.rstrip()) for l in lines)
            ch    = len(lines)
            tw    = ART_W + cw + 7
            x     = ((base_x + f // speed) % tw) - cw

            # Erase interior span, draw only actual chars
            for row_i, line in enumerate(lines):
                r = y_start + row_i
                if r < 0 or r >= ART_H - 1: continue
                stripped = line.rstrip()
                if not stripped: continue
                left  = next((i for i,c in enumerate(stripped) if c != ' '), None)
                right = len(stripped)
                if left is None: continue
                for col_i in range(left, right):
                    col = x + col_i
                    if 0 <= col < ART_W:
                        grid[r][col] = ' '
                for col_i, ch_c in enumerate(stripped):
                    if ch_c != ' ':
                        col = x + col_i
                        if 0 <= col < ART_W:
                            grid[r][col] = ch_c

        frame = [_p(''.join(row)) for row in grid]
        frame[ART_H - 1] = _p("       OVERCAST       ")
        frames.append(frame)
    return frames


# ── COMPUTED DROP GENERATOR ───────────────────────────────────────────────────
# Produces falling drop animations mathematically — no hand-drawing needed.
#
# Parameters:
#   W, H        canvas size (chars wide, lines tall)
#   drops       list of (col, speed, offset) tuples — one per drop column
#   chars       (head, body, tail, fade) — characters for the drop trail
#   dx          horizontal drift per frame (0=straight, 1=angled)
#   n_frames    how many frames to generate
#   cloud       optional list of lines to prepend above the drops
#   label       text label for bottom row

def _make_drops(W, H, drops, chars, dx, n_frames, cloud=None, label=""):
    """Generate n_frames of falling drop animation."""
    head_ch, body_ch, tail_ch, fade_ch = chars
    cloud_h = len(cloud) if cloud else 0
    drop_h  = H - cloud_h - 1   # rows for drops (full height minus label row)

    frames = []
    for f in range(n_frames):
        grid = [[" "] * W for _ in range(drop_h)]

        for col, speed, offset in drops:
            fall = (f // speed + offset) % drop_h
            for trail_row in range(4):
                row = fall - trail_row
                if row < 0 or row >= drop_h:
                    continue
                c = (col + f * dx) % W
                if   trail_row == 0: ch = head_ch
                elif trail_row == 1: ch = body_ch
                elif trail_row == 2: ch = tail_ch
                else:                ch = fade_ch
                grid[row][c] = ch

        frame_lines = []
        if cloud:
            frame_lines += cloud
        for row in grid:
            frame_lines.append(_p("".join(row)))
        frame_lines.append(_p(label.center(W)))
        frames.append(frame_lines[:H])

    return frames


# ── CLOUD SHAPES ──────────────────────────────────────────────────────────────
# Cloud transcribed from user's hand-drawn REXPaint art.
# 55 chars wide. Light cloud = full shape. Heavy cloud = denser base.

def _cloud_light():
    return [
        _p("                                           oo    oo "),
        _p("               ooo    ooooooo             oo    oo  "),
        _p("    o  ooo   ooo oo  oo      oo       ooooo  ooo    "),
        _p(" oo   oo  ooo      oo    oooo  oooooo o                "),
        _p("o  ooo oo  o        oooo o   oo                     "),
        _p("oo oo   ooo          oo   ooo                       "),
        _p("o   ooo  oo           ooo                           "),
        _p("ooooooooooooooooooooooooooooooooooooooooooooooooooooooo"),
    ]

def _cloud_heavy():
    return [
        _p("                                           oo    oo "),
        _p("               ooo    ooooooo             oo    oo  "),
        _p("    o  ooo   ooo oo  oo      oo       ooooo  ooo    "),
        _p(" oo   oo  ooo      oo    oooo  oooooo o               "),
        _p("o  ooo oo  o        oooo o   oo                     "),
        _p("oo oo   ooo          oo   ooo                       "),
        _p("oooooooooooooooooooooooooooooooooooooooooooooooooooooo"),
        _p("oooooooooooooooooooooooooooooooooooooooooooooooooooooo"),
    ]


def _make_precip(density, speed, chars, n_frames, label, seed):
    """Density-based precipitation — each cell independently triggered.
    density: 0.0-1.0 chance of a drop head on any given cell per frame
    speed: rows dropped per frame (higher = faster)
    chars: (head, body, tail)
    """
    import random
    rng = random.Random(seed)

    H = ART_H - 1
    W = ART_W

    # Pre-generate drop map — each column gets its own speed offset
    drop_cols = []
    for c in range(W):
        col_speed_offset = rng.randint(-1, 2)   # whole column shifts slightly
        col_drops = []
        n = max(1, int(density * H / 4))
        for i in range(n):
            start = rng.randint(0, H - 1)
            spd   = max(1, speed + col_speed_offset + rng.randint(0, 1))
            col_drops.append((start, spd))
        drop_cols.append(col_drops)

    frames = []
    for f in range(n_frames):
        grid = [[' '] * W for _ in range(H)]
        head_ch, body_ch, tail_ch = chars

        for c, col_drops in enumerate(drop_cols):
            for start, spd in col_drops:
                # Current head position
                pos = (start + f * spd) % H
                # Draw trail upward
                for trail in range(4):
                    r = pos - trail
                    if r < 0: r += H
                    if r >= H: continue
                    if   trail == 0: grid[r][c] = head_ch
                    elif trail == 1: grid[r][c] = body_ch
                    elif trail == 2: grid[r][c] = tail_ch

        frame = [_p(''.join(row)) for row in grid]
        frame.append(_p(label.center(W)))
        frames.append(frame[:ART_H])

    return frames


# ── DRIZZLE ───────────────────────────────────────────────────────────────────
def _drizzle():
    return _make_precip(density=0.3, speed=1, chars=(',', '.', ' '),
                        n_frames=12, label="DRIZZLE", seed=11)

# ── RAIN / SHOWERS ────────────────────────────────────────────────────────────
def _rain():
    return _make_precip(density=0.6, speed=2, chars=('|', '+', '.'),
                        n_frames=10, label="RAIN", seed=22)

def _showers():
    return _rain()

# ── HEAVY RAIN ────────────────────────────────────────────────────────────────
def _heavy_rain():
    return _make_precip(density=0.9, speed=3, chars=('|', '|', '+'),
                        n_frames=10, label="HEAVY RAIN", seed=33)

# ── SNOW ──────────────────────────────────────────────────────────────────────
def _snow():
    return _make_precip(density=0.4, speed=1, chars=('*', '.', ' '),
                        n_frames=14, label="SNOW", seed=44)

# ── BLIZZARD ──────────────────────────────────────────────────────────────────
def _blizzard():
    return _make_precip(density=1.0, speed=3, chars=('*', '*', '.'),
                        n_frames=10, label="BLIZZARD", seed=55)

# ── STORM ─────────────────────────────────────────────────────────────────────
def _storm():
    import random
    rng = random.Random(66)

    H = ART_H - 1
    W = ART_W
    n_frames = 12

    # Rain drop columns (blue)
    drop_cols = []
    for c in range(W):
        n = max(1, int(0.8 * H / 4))
        col_drops = []
        for i in range(n):
            col_drops.append((rng.randint(0, H-1), max(1, 3 + rng.randint(-1,1))))
        drop_cols.append(col_drops)

    # Lightning bolts evenly spaced across frames so at least one is always visible
    bolts = [
        (rng.randint(2, W-4), 0),
        (rng.randint(2, W-4), 3),
        (rng.randint(2, W-4), 7),
        (rng.randint(2, W-4), 10),
    ]

    LIGHTNING = ['<', '>', '<', '/']
    BOLT_LEN  = len(LIGHTNING)

    frames = []
    for f in range(n_frames):
        grid = [[' '] * W for _ in range(H)]

        for c, col_drops in enumerate(drop_cols):
            for start, spd in col_drops:
                pos = (start + f * spd) % H
                for trail in range(4):
                    r = pos - trail
                    if r < 0: r += H
                    if r >= H: continue
                    if   trail == 0: grid[r][c] = '|'
                    elif trail == 1: grid[r][c] = '+'
                    elif trail == 2: grid[r][c] = '.'

        frame = [_p(''.join(row)) for row in grid]
        frame.append(_p("THUNDERSTORM".center(W)))
        frame = frame[:ART_H]

        # Overlay lightning bolts — fall through full height each cycle
        for bolt_col, bolt_start in bolts:
            age = (f - bolt_start) % (H + BOLT_LEN)
            for i, ch in enumerate(LIGHTNING):
                r = age - BOLT_LEN + i
                if 0 <= r < ART_H - 1:
                    line = list(frame[r])
                    if bolt_col < len(line):
                        line[bolt_col] = ch
                    frame[r] = ''.join(line)

        frames.append(frame)

    return frames


# ── FOG — full canvas drifting mist bands ────────────────────────────────────

def _fog():
    frames = []
    # Two interleaved band patterns that scroll horizontally
    band_a = "░" * ART_W
    band_b = "▒" * ART_W
    band_c = " " * (ART_W // 4) + "░" * (ART_W // 2) + " " * (ART_W - ART_W // 4 - ART_W // 2)
    band_d = "▒" * (ART_W // 3) + " " * (ART_W // 4) + "░" * (ART_W - ART_W // 3 - ART_W // 4)

    # 8 frames — bands shift left 2 chars each frame
    for f in range(8):
        shift = f * 3
        frame = []
        bands = [band_a, band_b, band_c, band_d, band_a, band_b, band_c, band_d]
        # Rotate each band differently for depth
        for r in range(ART_H - 1):
            band = bands[r % len(bands)]
            s = (shift + r * 2) % ART_W
            rotated = band[s:] + band[:s]
            frame.append(_p(rotated))
        frame.append(_p("          FOG         "))
        frames.append(frame)
    return frames


# ─── Art table ────────────────────────────────────────────────────────────────

# ── NIGHT CLEAR — static stars, moon phase drawn live in draw_frame ───────────

def _night():
    import random
    rng = random.Random(99)
    W, H = ART_W, ART_H - 1

    grid = [[' '] * W for _ in range(H)]
    for _ in range(80):
        x, y = rng.randint(0, W-1), rng.randint(0, H-1)
        grid[y][x] = '*'

    frame = [_p(''.join(row)) for row in grid]
    frame.append(_p("      CLEAR NIGHT      "))
    return [frame[:ART_H]]


# ── NIGHT PARTLY CLOUDY — static stars + scrolling cloud ──────────────────────

def _night_cloudy():
    import random
    rng = random.Random(88)
    W, H = ART_W, ART_H - 1

    # Stars only — moon and clouds are drawn live in draw_frame
    # so the draw order (stars → moon → clouds) is guaranteed
    grid = [[' '] * W for _ in range(H)]
    for _ in range(80):
        x, y = rng.randint(0, W-1), rng.randint(0, H-1)
        grid[y][x] = '*'

    frame = [_p(''.join(row)) for row in grid]
    frame.append(_p("    PARTLY CLOUDY NIGHT    "))
    return [frame[:ART_H]]


ART = {
    "sunny":               {"frames": _sunny(),         "color": "yellow"},
    "partly_cloudy":       {"frames": _partly_cloudy(),  "color": "yellow"},
    "cloudy":              {"frames": _cloudy(),          "color": "white"},
    "drizzle":             {"frames": _drizzle(),         "color": "cyan"},
    "rain":                {"frames": _rain(),            "color": "cyan"},
    "heavy_rain":          {"frames": _heavy_rain(),      "color": "cyan"},
    "showers":             {"frames": _showers(),         "color": "cyan"},
    "snow":                {"frames": _snow(),            "color": "white"},
    "blizzard":            {"frames": _blizzard(),        "color": "white"},
    "storm":               {"frames": _storm(),           "color": "blue"},
    "fog":                 {"frames": _fog(),             "color": "white"},
    "night":               {"frames": _night(),           "color": "white"},
    "night_partly_cloudy": {"frames": _night_cloudy(),    "color": "white"},
}

# ─── Weather API ──────────────────────────────────────────────────────────────

def location_to_coords(location, country="", force_latin=False):
    """Resolve a location string to (lat, lon, display_name, country_code).

    Tries three strategies in order:
      1. Postal code lookup  (fast, precise — works for ZIP, postcode, etc.)
      2. Free-text city search with country filter  (e.g. "London" + "gb")
      3. Free-text city search globally  (fallback, no country filter)

    Returns: (lat, lon, city_name, country_code)
    """
    def _search(params):
        params.update({"format": "json", "limit": 1,
                        "addressdetails": 1})
        req = urllib.request.Request(
            "https://nominatim.openstreetmap.org/search?"
            + urllib.parse.urlencode(params),
            headers={"User-Agent": "StormShell/1.0"},
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read())

    data = []

    # Strategy 1 — postal code
    p = {"postalcode": location}
    if country:
        p["country"] = country
    elif location.replace(" ", "").isdigit():
        p["country"] = DEFAULT_COUNTRY or "us"
    try:
        data = _search(p)
    except Exception:
        pass

    # Strategy 2 — city name with country
    if not data and country:
        try:
            data = _search({"q": location, "countrycodes": country})
        except Exception:
            pass

    # Strategy 3 — city name global, only skip if input is all digits (zip code)
    is_postal = location.replace(" ", "").isdigit()
    if not data and not is_postal:
        try:
            data = _search({"q": location})
        except Exception:
            pass

    if not data:
        raise ValueError(
            f"Could not find '{location}'"
            + (f" in country '{country}'" if country else "")
            + ". Try a city name or add --country CC."
        )

    item    = data[0]
    addr    = item.get("address", {})
    cc      = addr.get("country_code", "").lower()

    # Build a clean display name: prefer city/town/village, fall back to
    # the first segment of the full display_name string
    # Prefer native language name — looks great on SSH terminals which handle
    # unicode. On raw TTY the Uni Terminus font covers Latin + box-draw but
    # addr dict reliably has city/town/village for all location types
    # Only fall back to display_name if addr has nothing useful
    city = (addr.get("city")
            or addr.get("town")
            or addr.get("village")
            or addr.get("municipality")
            or addr.get("suburb")
            or addr.get("city_district")
            or addr.get("county")
            or addr.get("province")
            or addr.get("state_district")
            or addr.get("region")
            or addr.get("state"))

    if not city:
        for part in item.get("display_name", location).split(","):
            part = part.strip()
            if part and not part.replace(" ", "").isdigit():
                city = part
                break

    if not city:
        city = location

    # If city name contains non-Latin characters (Hebrew, Arabic, CJK etc.)
    # the Uni Terminus TTY font will show diamonds. Re-fetch with English.
    def _is_latin(s):
        try:
            s.encode("latin-1")
            return True
        except (UnicodeEncodeError, AttributeError):
            return False
        return all(ord(c) < 0x0250 or c in " -'." for c in s)

    if force_latin and not _is_latin(city):
        try:
            en_params = {"q": location, "format": "json", "limit": 1,
                         "addressdetails": 1, "accept-language": "en"}
            if country:
                en_params["countrycodes"] = country
            en_req = urllib.request.Request(
                "https://nominatim.openstreetmap.org/search?"
                + urllib.parse.urlencode(en_params),
                headers={"User-Agent": "StormShell/1.0",
                         "Accept-Language": "en"},
            )
            with urllib.request.urlopen(en_req, timeout=10) as r:
                en_data = json.loads(r.read())
            if en_data:
                en_addr = en_data[0].get("address", {})
                en_city = (en_addr.get("city") or en_addr.get("town")
                           or en_addr.get("village") or en_addr.get("municipality")
                           or en_addr.get("suburb") or en_addr.get("city_district")
                           or en_addr.get("county") or en_addr.get("province")
                           or en_addr.get("state_district") or en_addr.get("region")
                           or en_addr.get("state"))
                if en_city and _is_latin(en_city):
                    city = en_city
        except Exception:
            city = ''.join(c for c in city if ord(c) < 0x0250 or c in " -'.").strip() or location

    return float(item["lat"]), float(item["lon"]), city, cc


def fetch_weather(lat, lon):
    params = urllib.parse.urlencode({
        "latitude":         lat,
        "longitude":        lon,
        "current": ",".join([
            "temperature_2m", "apparent_temperature",
            "relative_humidity_2m", "wind_speed_10m",
            "wind_direction_10m", "weather_code",
            "surface_pressure",
        ]),
        "hourly":           "temperature_2m,weather_code,precipitation_probability,surface_pressure",
        "daily":            "sunrise,sunset",
        "temperature_unit": TEMP_UNIT,
        "wind_speed_unit":  WIND_UNIT,
        "timezone":         "auto",
        "forecast_days":    2,
    })
    with urllib.request.urlopen(
        f"https://api.open-meteo.com/v1/forecast?{params}", timeout=10
    ) as r:
        return json.loads(r.read())


def fetch_aqi(lat, lon):
    """Fetch current US AQI and pollen from Open-Meteo air quality API."""
    params = urllib.parse.urlencode({
        "latitude":  lat,
        "longitude": lon,
        "current":   "us_aqi,pm2_5,alder_pollen,birch_pollen,grass_pollen,mugwort_pollen,olive_pollen,ragweed_pollen",
        "timezone":  "auto",
    })
    try:
        with urllib.request.urlopen(
            f"https://air-quality-api.open-meteo.com/v1/air-quality?{params}",
            timeout=8
        ) as r:
            data = json.loads(r.read())
        c    = data["current"]
        aqi  = c.get("us_aqi", None)
        pm25 = c.get("pm2_5", None)
        if aqi is None:
            return None
        if   aqi <= 50:  cat, col = "Good",              "green"
        elif aqi <= 100: cat, col = "Moderate",          "yellow"
        elif aqi <= 150: cat, col = "Unhealthy (sens.)", "orange"
        elif aqi <= 200: cat, col = "Unhealthy",         "red"
        elif aqi <= 300: cat, col = "Very Unhealthy",    "red"
        else:            cat, col = "Hazardous",         "red"

        # Pollen — find dominant type
        pollen_types = {
            "Tree":    max(c.get("alder_pollen") or 0, c.get("birch_pollen") or 0, c.get("olive_pollen") or 0),
            "Grass":   c.get("grass_pollen") or 0,
            "Weed":    max(c.get("mugwort_pollen") or 0, c.get("ragweed_pollen") or 0),
        }
        dom_type  = max(pollen_types, key=pollen_types.get)
        dom_value = pollen_types[dom_type]
        if   dom_value == 0:   pollen = None
        elif dom_value < 10:   pollen = {"type": dom_type, "level": "Low",       "value": int(dom_value)}
        elif dom_value < 50:   pollen = {"type": dom_type, "level": "Medium",    "value": int(dom_value)}
        elif dom_value < 200:  pollen = {"type": dom_type, "level": "High",      "value": int(dom_value)}
        else:                  pollen = {"type": dom_type, "level": "Very High",  "value": int(dom_value)}

        return {"aqi": aqi, "cat": cat, "col": col, "pm25": pm25, "pollen": pollen}
    except Exception:
        return None


    return ["N","NE","E","SE","S","SW","W","NW"][round(deg / 45) % 8]


def moon_phase(dt=None):
    """Return (phase_name, phase_index) for the current moon phase.
    phase_index: 0=New Moon ... 7=Waning Crescent
    Pure math — no API needed."""
    if dt is None:
        dt = datetime.now()
    known_new = datetime(2000, 1, 6, 18, 14)
    elapsed   = (dt - known_new).total_seconds()
    cycle     = 29.53058867 * 24 * 3600
    phase_pct = (elapsed % cycle) / cycle

    phases = [
        (0.0,  0.03, "New Moon",        0),
        (0.03, 0.22, "Waxing Crescent", 1),
        (0.22, 0.28, "First Quarter",   2),
        (0.28, 0.47, "Waxing Gibbous",  3),
        (0.47, 0.53, "Full Moon",       4),
        (0.53, 0.72, "Waning Gibbous",  5),
        (0.72, 0.78, "Last Quarter",    6),
        (0.78, 0.97, "Waning Crescent", 7),
        (0.97, 1.0,  "New Moon",        0),
    ]
    for lo, hi, name, idx in phases:
        if lo <= phase_pct < hi:
            return name, idx
    return "New Moon", 0


def moon_calendar(dt=None):
    """Return list of (phase_name, phase_idx, date_str, is_current) for all
    8 phases showing the next occurrence of each from today.
    Dots pattern: wax up 1-8, wane back down symmetrically."""
    from datetime import timedelta
    if dt is None:
        dt = datetime.now()

    known_new = datetime(2000, 1, 6, 18, 14)
    cycle_sec = 29.53058867 * 24 * 3600
    elapsed   = (dt - known_new).total_seconds()
    cycle_pct = (elapsed % cycle_sec) / cycle_sec

    # Phase center offsets within the cycle (0.0 = new moon)
    phase_offsets = [0.0, 0.125, 0.25, 0.375, 0.5, 0.625, 0.75, 0.875]
    phase_names   = [
        "New Moon", "Waxing Crescent", "First Quarter", "Waxing Gibbous",
        "Full Moon", "Waning Gibbous", "Last Quarter", "Waning Crescent",
    ]
    # Dots filled per phase — wax up to 8, wane back down
    dot_counts    = [1, 2, 3, 4, 8, 6, 4, 2]

    current_name, current_idx = moon_phase(dt)

    rows = []
    for i, (name, offset, dots) in enumerate(zip(phase_names, phase_offsets, dot_counts)):
        # How far ahead (in cycle fraction) is this phase from now?
        diff = (offset - cycle_pct) % 1.0
        # Convert to a future date
        future_dt  = dt + timedelta(seconds=diff * cycle_sec)
        date_str   = future_dt.strftime("%b %d")
        is_current = (i == current_idx)
        rows.append((name, i, dots, date_str, is_current))

    return rows


def _wind_dir(deg):
    return ["N","NE","E","SE","S","SW","W","NW"][round(deg / 45) % 8]


def parse_weather(data):
    c    = data["current"]
    h    = data["hourly"]
    d    = data.get("daily", {})
    unit = "F" if TEMP_UNIT == "fahrenheit" else "C"
    wsym = {"mph": "mph", "kmh": "km/h", "ms": "m/s", "kn": "kn"}.get(WIND_UNIT, WIND_UNIT)

    now_str   = data["current"]["time"][:13]
    now_index = 0
    for i, t in enumerate(h["time"]):
        if t.startswith(now_str):
            now_index = i
            break

    precip_prob = h.get("precipitation_probability") or [0] * len(h["time"])
    forecast    = []
    for offset in range(1, 7):
        idx = now_index + offset
        if idx >= len(h["time"]):
            break
        t = datetime.fromisoformat(h["time"][idx])
        forecast.append({
            "label":      t.strftime("%-I%p").lower(),
            "temp":       f"{h['temperature_2m'][idx]:.0f}{unit}",
            "code":       h["weather_code"][idx],
            "precip_pct": precip_prob[idx],
        })

    # Sunrise / sunset — strip date, keep HH:MM
    def _hhmm(iso_str):
        try:
            return datetime.fromisoformat(iso_str).strftime("%H:%M")
        except Exception:
            return "--:--"

    sunrise = _hhmm(d.get("sunrise", [""])[0]) if d.get("sunrise") else "--:--"
    sunset  = _hhmm(d.get("sunset",  [""])[0]) if d.get("sunset")  else "--:--"

    phase_name, phase_idx = moon_phase()

    # Pressure trend — compare now vs 3 hours ago
    pressure_now = c.get("surface_pressure")
    pressure_3h  = None
    if pressure_now is not None and "surface_pressure" in h:
        idx_3h = max(0, now_index - 3)
        pressure_3h = h["surface_pressure"][idx_3h]

    if pressure_now is not None and pressure_3h is not None:
        change = pressure_now - pressure_3h
        if   change >  1.0: trend, trend_dir = "Rising",  "up"
        elif change < -1.0: trend, trend_dir = "Falling", "down"
        else:               trend, trend_dir = "Steady",  "flat"
        pressure_data = {
            "hpa":    round(pressure_now, 1),
            "change": round(change, 1),
            "trend":  trend,
            "dir":    trend_dir,
        }
    else:
        pressure_data = None

    return {
        "temp":        f"{c['temperature_2m']:.0f}{unit}",
        "feels_like":  f"{c['apparent_temperature']:.0f}{unit}",
        "humidity":    f"{c['relative_humidity_2m']:.0f}%",
        "wind":        f"{c['wind_speed_10m']:.0f} {wsym} {_wind_dir(c.get('wind_direction_10m', 0))}",
        "condition":   wmo_to_condition(c["weather_code"]),
        "forecast":    forecast,
        "sunrise":     sunrise,
        "sunset":      sunset,
        "moon_name":   phase_name,
        "pressure":    pressure_data,
    }

# ─── Color pairs ──────────────────────────────────────────────────────────────

CP_YELLOW = 1
CP_CYAN   = 2
CP_WHITE  = 3
CP_GREEN  = 4
CP_RED    = 5
CP_DIM    = 6
CP_TITLE  = 7
CP_BLUE   = 8
CP_ORANGE = 9

COLOR_MAP = {
    "yellow": CP_YELLOW,
    "cyan":   CP_CYAN,
    "white":  CP_WHITE,
    "red":    CP_RED,
    "blue":   CP_BLUE,
}

def init_colors():
    curses.start_color()
    curses.use_default_colors()
    curses.init_pair(CP_YELLOW, curses.COLOR_YELLOW,  -1)
    curses.init_pair(CP_CYAN,   curses.COLOR_CYAN,    -1)
    curses.init_pair(CP_WHITE,  curses.COLOR_WHITE,   -1)
    curses.init_pair(CP_GREEN,  curses.COLOR_GREEN,   -1)
    curses.init_pair(CP_RED,    curses.COLOR_RED,     -1)
    curses.init_pair(CP_DIM,    curses.COLOR_WHITE,   -1)
    curses.init_pair(CP_TITLE,  curses.COLOR_BLACK,   curses.COLOR_CYAN)
    curses.init_pair(CP_BLUE,   curses.COLOR_BLUE,    -1)
    # Orange — color 208 in 256-color terminals, falls back to yellow
    try:
        curses.init_pair(CP_ORANGE, 208, -1)
    except Exception:
        curses.init_pair(CP_ORANGE, curses.COLOR_YELLOW, -1)

# ─── Drawing helpers ──────────────────────────────────────────────────────────

def ws(win, y, x, text, attr=0):
    """Bounds-safe addstr — never raises, fills to last column."""
    h, w = win.getmaxyx()
    if y < 0 or y >= h or x < 0 or x >= w:
        return
    text = str(text)[:max(0, w - x)]
    try:
        if x + len(text) >= w:
            # Write all but last char normally, then use insnstr for last
            if len(text) > 1:
                win.addstr(y, x, text[:-1], attr)
            win.insnstr(y, x + len(text) - 1, text[-1], 1, attr)
        else:
            win.addstr(y, x, text, attr)
    except curses.error:
        pass


def precip_bar(pct, width=10):
    filled = round(pct / 100 * width)
    return "▓" * filled + "░" * (width - filled)

# ─── Main draw frame ──────────────────────────────────────────────────────────

def draw_frame(win, weather, location, frame_idx, last_updated, status_msg):
    win.erase()
    h, w = win.getmaxyx()

    cond      = weather["condition"]

    # Switch to night animation if between sunset and sunrise
    try:
        now_hm    = datetime.now().strftime("%H:%M")
        sunrise   = weather.get("sunrise", "06:00")
        sunset    = weather.get("sunset",  "20:00")
        is_night  = now_hm < sunrise or now_hm >= sunset
    except Exception:
        is_night  = False

    if is_night and cond == "sunny":
        cond = "night"
    elif is_night and cond == "partly_cloudy":
        cond = "night_partly_cloudy"

    art_def   = ART.get(cond, ART["cloudy"])
    art_color = curses.color_pair(COLOR_MAP.get(art_def["color"], CP_WHITE))
    frame     = art_def["frames"][frame_idx % len(art_def["frames"])]

    # ── Layout geometry ───────────────────────────────────────────────────────
    wide    = (w >= 60)
    div_x   = max(28, w // 3)      # divider — left third of screen
    left_w  = div_x - 1
    right_x = div_x + 2
    right_w = w - right_x - 1

    # ── 5-row ASCII digit art ─────────────────────────────────────────────────
    # Each glyph is 5 chars wide x 5 rows tall.
    # Degree sign is a small top-corner ornament: sits rows 0-1, blank rows 2-4
    _BIG5 = {
        '0': [' ___ ', '|   |', '|   |', '|   |', '|___|'],
        '1': ['     ', '  |  ', '  |  ', '  |  ', '  |  '],
        '2': [' ___ ', '    |', ' ___|', '|    ', '|____'],
        '3': [' ___ ', '    |', ' ___|', '    |', ' ___|'],
        '4': ['     ', '|   |', '|___|', '    |', '    |'],
        '5': [' ____', '|    ', '|___ ', '    |', ' ___|'],
        '6': [' ___ ', '|    ', '|___ ', '|   |', '|___|'],
        '7': [' ____', '    |', '    |', '    |', '    |'],
        '8': [' ___ ', '|   |', '|___|', '|   |', '|___|'],
        '9': [' ___ ', '|   |', '|___|', '    |', ' ___|'],
        '-': ['     ', '     ', ' ___ ', '     ', '     '],
        ' ': ['     ', '     ', '     ', '     ', '     '],
        # degree sign — square style, top aligned with digit tops
        'o': [' _  ', '[_] ', '    ', '    ', '    '],
    }

    def big_render(text):
        """Return 5 strings — rows of big-digit art for `text`."""
        t = text.upper().rstrip('FC').strip() + 'o'
        rows = [''] * 5
        for ch in t:
            g = _BIG5.get(ch, _BIG5[' '])
            for i in range(5):
                rows[i] += g[i] + ' '
        return rows

    # ── Title bar ─────────────────────────────────────────────────────────────
    ws(win, 0, 0, " " * w, curses.color_pair(CP_TITLE))
    ws(win, 0, 2, f"StormShell  |  {location.upper()}"[:w - 2],
       curses.color_pair(CP_TITLE) | curses.A_BOLD)

    # ── Vertical divider ──────────────────────────────────────────────────────
    if wide:
        for row in range(1, h - 2):
            ws(win, row, div_x, "|", curses.color_pair(CP_DIM))

    # ═══════════════════════════════════════════════════════════════════════════
    # LEFT PANEL — primary data, large and readable
    # ═══════════════════════════════════════════════════════════════════════════
    row = 2

    # City name — bold, underlined, tight gap below
    city = location.upper()[:left_w - 2]
    ws(win, row,     2, city,
       curses.color_pair(CP_YELLOW) | curses.A_BOLD)
    ws(win, row + 1, 2, "-" * len(city),
       curses.color_pair(CP_DIM))
    row += 2          # tighter — temp comes up closer to city

    # Temperature — 5-row big digit art
    temp_str  = weather["temp"]
    feels_str = weather["feels_like"].rstrip('FC').strip()
    temp_rows = big_render(temp_str)
    for i, r in enumerate(temp_rows):
        ws(win, row + i, 2, r[:left_w - 2],
           curses.color_pair(CP_YELLOW) | curses.A_BOLD)
    row += 6          # 5 digit rows + 1 blank

    # Feels like, humidity, wind — centered, no color
    feels_line = f"feels like  {feels_str}"
    humid_line = f"Humidity    {weather['humidity']}"
    wind_line  = f"Wind        {weather['wind']}"
    ws(win, row,     2, feels_line, curses.color_pair(CP_DIM))
    ws(win, row + 1, 2, humid_line, curses.color_pair(CP_DIM))
    ws(win, row + 2, 2, wind_line,  curses.color_pair(CP_DIM))
    row += 4

    # Forecast
    ws(win, row, 2, "+- FORECAST --------+", curses.color_pair(CP_CYAN))
    row += 1
    ws(win, row, 2, "| TIME  COND  TEMP  |", curses.color_pair(CP_DIM))
    row += 1

    for fc in weather.get("forecast", [])[:4]:
        icon = FC_ICON.get(wmo_to_condition(fc["code"]), "???")
        pct  = fc["precip_pct"]
        line = f"| {fc['label']:>4}  {icon}  {fc['temp']:>5}  |"
        line = line[:21].ljust(21)
        if pct >= 70:   attr = curses.color_pair(CP_CYAN)
        elif pct >= 30: attr = curses.color_pair(CP_WHITE)
        else:           attr = curses.color_pair(CP_GREEN)
        ws(win, row, 2, line[:left_w], attr)
        row += 1

    ws(win, row, 2, "+-------------------+", curses.color_pair(CP_CYAN))

    # Pollen widget — right of forecast box, top-aligned
    pollen = (weather.get("aqi") or {}).get("pollen")
    if pollen:
        p_col = 24
        p_row = row - 5   # align with top of forecast data rows
        level_color = {
            "Low":       curses.color_pair(CP_GREEN),
            "Medium":    curses.color_pair(CP_YELLOW),
            "High":      curses.color_pair(CP_ORANGE),
            "Very High": curses.color_pair(CP_RED),
        }.get(pollen["level"], curses.color_pair(CP_WHITE))
        ws(win, p_row,     p_col, "POLLEN", curses.color_pair(CP_DIM))
        ws(win, p_row + 1, p_col, pollen["type"],  curses.color_pair(CP_WHITE) | curses.A_BOLD)
        ws(win, p_row + 2, p_col, pollen["level"], level_color | curses.A_BOLD)

    row += 2   # restored gap before AQI

    # ── AQI bar ───────────────────────────────────────────────────────────────
    aqi_data = weather.get("aqi")
    if aqi_data:
        aqi    = aqi_data["aqi"]
        cat    = aqi_data["cat"]
        bar_w  = left_w - 4
        scale  = 200           # cap — anything over 200 fills the bar
        capped = min(aqi, scale)

        # Band boundaries on 0-200 scale:
        #   0- 50  green   (Good)
        #  51-100  yellow  (Moderate)
        # 101-150  orange  (Unhealthy for sensitive)
        # 151-200  red     (Unhealthy+)
        band_chars = bar_w / scale
        g_end = round(50  * band_chars)   # green ends here
        y_end = round(100 * band_chars)   # yellow ends here
        o_end = round(150 * band_chars)   # orange ends here
        # rest is red

        filled = round(capped / scale * bar_w)

        def band(start, end, cp):
            seg_fill  = max(0, min(filled, end) - start)
            seg_empty = max(0, end - start - seg_fill)
            return ("█" * seg_fill + "░" * seg_empty, cp)

        segments = [
            band(0,     g_end, curses.color_pair(CP_GREEN)),
            band(g_end, y_end, curses.color_pair(CP_YELLOW)),
            band(y_end, o_end, curses.color_pair(CP_ORANGE)),
            band(o_end, bar_w, curses.color_pair(CP_RED)),
        ]

        # AQI label color matches current band
        if   aqi <= 50:  label_attr = curses.color_pair(CP_GREEN)
        elif aqi <= 100: label_attr = curses.color_pair(CP_YELLOW)
        elif aqi <= 150: label_attr = curses.color_pair(CP_ORANGE)
        else:            label_attr = curses.color_pair(CP_RED)

        ws(win, row, 2, "AIR QUALITY", curses.color_pair(CP_DIM))
        col = 2
        for seg_str, seg_attr in segments:
            ws(win, row + 1, col, seg_str, seg_attr | curses.A_BOLD)
            col += len(seg_str)
        ws(win, row + 2, 2, f"AQI {aqi}  {cat}", label_attr)

    # ═══════════════════════════════════════════════════════════════════════════
    # RIGHT PANEL — top: animation   bottom: clock (left) + moon calendar (right)
    # ═══════════════════════════════════════════════════════════════════════════
    if wide:
        BOX_H   = 14
        anim_h  = h - 2 - BOX_H - 1   # one less padding = fills to divider
        box_top = h - 2 - BOX_H

        # Horizontal divider
        ws(win, box_top, div_x, "+", curses.color_pair(CP_DIM))
        ws(win, box_top, div_x + 1, "-" * (w - div_x - 2),
           curses.color_pair(CP_DIM))

        # ── Animation (upper right) ───────────────────────────────────────────
        art_rows  = min(len(frame), anim_h)
        art_start = 1   # row 0 is title bar — start animation at row 1
        LIGHTNING_CHARS = set('<>/')
        for i, line in enumerate(frame[:art_rows]):
            row_y = art_start + i
            if row_y >= box_top: break   # don't draw into clock panel
            ws(win, row_y, right_x,
               line[:right_w].ljust(right_w), art_color | curses.A_BOLD)
            # Overlay lightning chars in yellow
            for ci, ch in enumerate(line[:right_w]):
                if ch in LIGHTNING_CHARS:
                    ws(win, row_y, right_x + ci, ch,
                       curses.color_pair(CP_YELLOW) | curses.A_BOLD)

        # Live cloud overlay for partly_cloudy — independent looping clouds
        if cond == "partly_cloudy":
            import random as _rnd
            rng_pc = _rnd.Random(42)
            c1_shape = 3;  c1_y = rng_pc.randint(1, 3)
            c2_shape = rng_pc.choice([0, 4]);  c2_y = rng_pc.randint(2, 5)
            c3_shape = rng_pc.choice([1, 2]);  c3_y = rng_pc.randint(1, 4)
            c1_w = max(len(l.rstrip()) for l in _CLOUD_SHAPES[c1_shape])
            c2_w = max(len(l.rstrip()) for l in _CLOUD_SHAPES[c2_shape])
            c3_w = max(len(l.rstrip()) for l in _CLOUD_SHAPES[c3_shape])
            c1_total = right_w + c1_w + 2
            c2_total = right_w + c2_w + 2
            c3_total = right_w + c3_w + 2

            def _draw_pc_cloud(shape, cy, cx):
                for row_i, line in enumerate(_CLOUD_SHAPES[shape]):
                    r = art_start + cy + row_i
                    if r < art_start + 1 or r >= box_top: continue
                    stripped = line.rstrip()
                    if not stripped: continue
                    left = next((i for i, c in enumerate(stripped) if c != ' '), None)
                    if left is None: continue
                    for col_i in range(left, len(stripped)):
                        col = right_x + cx + col_i
                        if right_x <= col < right_x + right_w:
                            ws(win, r, col, ' ', art_color)
                    for col_i, ch in enumerate(stripped):
                        if ch != ' ':
                            col = right_x + cx + col_i
                            if right_x <= col < right_x + right_w:
                                ws(win, r, col, ch, art_color | curses.A_BOLD)

            _draw_pc_cloud(c1_shape, c1_y, (frame_idx // 3 % c1_total) - c1_w)
            _draw_pc_cloud(c2_shape, c2_y, (frame_idx // 2 % c2_total) - c2_w)
            _draw_pc_cloud(c3_shape, c3_y, (frame_idx // 4 % c3_total) - c3_w)
        if cond in ("night", "night_partly_cloudy"):
            night_moon_art = {
                "New Moon":        ("   ____  ", "  /    \\ ", " |      |", "  \\____/ "),
                "Waxing Crescent": ("   ____  ", "   \\   \\ ", "    )   |", "   /___/ "),
                "First Quarter":   ("   _____ ", "  /  |  \\", " |   |   |", "  \\__|__/ "),
                "Full Moon":       ("   ____  ", "  /    \\ ", " |      |", "  \\____/ "),
                "Waxing Gibbous":  ("    ___  ", "   |   \\ ", "    |   |", "   |___/ "),
                "Waning Gibbous":  ("    ___  ", "   /   | ", "  |   |  ", "   \\___|  "),
                "Last Quarter":    ("   _____ ", "  /  |  \\", " |   |   |", "  \\__|__/ "),
                "Waning Crescent": ("   ____  ", "  /   /  ", " |   (   ", "  \\___\\  "),
            }
            moon_nm  = weather.get("moon_name", "Full Moon")
            n_art    = night_moon_art.get(moon_nm, night_moon_art["Full Moon"])
            n_is_new = moon_nm == "New Moon"
            n_color  = curses.color_pair(CP_BLUE) if n_is_new else curses.color_pair(CP_YELLOW)
            n_x = right_x + (right_w - 9) // 2 + 5
            n_y = art_start + 1
            for li, line in enumerate(n_art):
                row_y = n_y + li
                if row_y >= box_top: break
                ws(win, row_y, n_x, line, n_color | curses.A_BOLD)

            # Draw clouds on top of moon for partly cloudy night
            if cond == "night_partly_cloudy":
                import random as _rng
                rng2 = _rng.Random(88)
                nc_W = right_w
                c1_shape = 3
                c1_y     = rng2.randint(0, 2)
                c1_w     = max(len(l.rstrip()) for l in _CLOUD_SHAPES[c1_shape])
                c2_shape = 0
                c2_y     = c1_y + rng2.randint(0, 1)
                c2_w     = max(len(l.rstrip()) for l in _CLOUD_SHAPES[c2_shape])
                c2_off   = (nc_W + c1_w + 7) // 3
                c2_spd   = 2
                total_nc = nc_W + c2_w + 7 + c2_off

                def _draw_nc_cloud(shape, cy, cx):
                    for row_i, line in enumerate(_CLOUD_SHAPES[shape]):
                        r = art_start + cy + row_i
                        if r < 0 or r >= box_top: continue
                        stripped = line.rstrip()
                        if not stripped: continue
                        left = next((i for i, c in enumerate(stripped) if c != ' '), None)
                        if left is None: continue
                        for col_i in range(left, len(stripped)):
                            col = right_x + cx + col_i
                            if right_x <= col < right_x + right_w:
                                ws(win, r, col, ' ', art_color)
                        for col_i, ch in enumerate(stripped):
                            if ch != ' ':
                                col = right_x + cx + col_i
                                if right_x <= col < right_x + right_w:
                                    ws(win, r, col, ch, art_color | curses.A_BOLD)

                f = frame_idx
                c1_total = right_w + c1_w + 2
                c2_total = right_w + c2_w + 2
                _draw_nc_cloud(c1_shape, c1_y,     (f // 3 % c1_total) - c1_w)
                _draw_nc_cloud(c2_shape, c2_y + 1, (f // 2 % c2_total) - c2_w)

            # Clouds already rendered in animation frames — no redraw needed

        # ── Clock (left of bottom box, with padding) ──────────────────────────
        now       = datetime.now()
        clock_col = right_x + 2
        draw_clock(win, box_top + 1, clock_col, now)   # moved up 1 row

        # Countries that use 12-hour AM/PM format
        AMPM_COUNTRIES = {"us", "ca", "au", "nz", "ph", "eg", "sa", "pk", "in"}
        use_ampm  = weather.get("cc", DEFAULT_COUNTRY).lower() in AMPM_COUNTRIES

        date_str  = now.strftime("%A %B %-d %Y").upper()
        time_str  = now.strftime("%I:%M:%S %p") if use_ampm else now.strftime("%H:%M:%S")

        # Center date and time under the clock
        # Clock midpoint is clock_col + 10 (clock is 21 wide)
        clock_mid = clock_col + 10
        date_col  = clock_mid - len(date_str) // 2
        time_col  = clock_mid - len(time_str) // 2

        ws(win, box_top + 12, date_col, date_str,
           curses.color_pair(CP_WHITE) | curses.A_BOLD)
        ws(win, box_top + 13, time_col, time_str,
           curses.color_pair(CP_DIM))

        # ── Moon + sunrise/sunset (right of clock) ───────────────────────────
        moon_x    = clock_col + 29
        moon_name = weather.get("moon_name", "")
        rise      = weather.get("sunrise", "--:--")
        sset      = weather.get("sunset",  "--:--")

        # Moon art exactly as designed by user — (line1, line2, line3, line4)
        # For split phases, each line is (shadow_part, lit_part) drawn separately
        moon_art = {
            "New Moon":        ("   ____  ", "  /    \\ ", " |      |", "  \\____/ "),
            "Waxing Crescent": ("   ____  ", "   \\   \\ ", "    )   |", "   /___/ "),
            "First Quarter":   ("   _____ ", "  /  |  \\", " |   |   |", "  \\__|__/ "),
            "Full Moon":       ("   ____  ", "  /    \\ ", " |      |", "  \\____/ "),
            "Waxing Gibbous":  ("    ___  ", "   |   \\ ", "    |   |", "   |___/ "),
            "Waning Gibbous":  ("    ___  ", "   /   | ", "  |   |  ", "   \\___|  "),
            "Last Quarter":    ("   _____ ", "  /  |  \\", " |   |   |", "  \\__|__/ "),
            "Waning Crescent": ("   ____  ", "  /   /  ", " |   (   ", "  \\___\\  "),
        }

        # Split points for quarter phases — index of | in each line
        quarter_splits = {
            "First Quarter":  [None, 4, 4, 4],   # split col relative to line start
            "Last Quarter":   [None, 4, 4, 4],
        }

        art      = moon_art.get(moon_name, moon_art["New Moon"])

        sun_rise_str = f" Sunrise:  {rise}"
        sun_set_str  = f" Sunset:   {sset}"
        # widget_w still needed for pres_x calculation
        widget_w     = max(len(l) for l in list(art)
                           + [moon_name, sun_rise_str, sun_set_str, "MOON"])

        # New moon = all blue, full moon = all yellow
        # Quarters = per-character color maps from user design
        is_new     = moon_name == "New Moon"
        is_quarter = moon_name in ("First Quarter", "Last Quarter")
        base_color = curses.color_pair(CP_BLUE) if is_new else curses.color_pair(CP_YELLOW)

        # Per-character color maps for quarter phases (y=yellow, b=blue, d=dim)
        quarter_colors = {
            "First Quarter": [
                list('dddbbyyyd'),
                list('bbbbbybby'),
                list('bbbbbyyyyy'),
                list('bbbbbyyyyd'),
            ],
            "Last Quarter": [
                list('dddyyybbd'),
                list('bbybbybbbb'),
                list('yyyyyybbb b'),
                list('yyyyyyyybd'),
            ],
        }
        # Fix Last Quarter row 2 — 10 chars
        quarter_colors["Last Quarter"][2] = list('yyyyyybbbb')

        color_map = {'y': curses.color_pair(CP_YELLOW) | curses.A_BOLD,
                     'b': curses.color_pair(CP_BLUE)   | curses.A_BOLD,
                     'd': curses.color_pair(CP_DIM)    | curses.A_BOLD}

        # MOON label — stays at moon_x (user confirmed correct position)
        ws(win, box_top + 3, moon_x, "MOON",
           curses.color_pair(CP_DIM))

        # Art rows — 3 spaces left of moon_x
        art_x = moon_x - 3
        for i, line in enumerate(art):
            row = box_top + 4 + i
            if is_quarter:
                cmap = quarter_colors[moon_name][i]
                # Draw char by char grouping consecutive same-color runs
                j = 0
                while j < len(line):
                    c = cmap[j] if j < len(cmap) else 'd'
                    k = j + 1
                    while k < len(line) and (k >= len(cmap) and c == 'd' or k < len(cmap) and cmap[k] == c):
                        k += 1
                    ws(win, row, art_x + j, line[j:k], color_map[c])
                    j = k
            else:
                ws(win, row, art_x, line, base_color | curses.A_BOLD)

        # Phase name + sunrise/sunset — 4 spaces left of moon_x
        txt_x = moon_x - 4
        ws(win, box_top + 9,  txt_x, moon_name,    curses.color_pair(CP_DIM))
        ws(win, box_top + 11, txt_x - 1, sun_rise_str, curses.color_pair(CP_WHITE))
        ws(win, box_top + 12, txt_x - 1, sun_set_str,  curses.color_pair(CP_WHITE))

        # ── Pressure widget — to the right of moon ───────────────────────────
        pdata  = weather.get("pressure")
        pres_x = moon_x + widget_w + 2   # two extra spaces before pressure

        if pdata and pres_x < w - 14:
            hpa    = pdata["hpa"]
            change = pdata["change"]
            trend  = pdata["trend"]
            dirn   = pdata["dir"]

            if   dirn == "up":   p_attr = curses.color_pair(CP_YELLOW); needle = ["  .---.", " ( --> )", "'-------'"]
            elif dirn == "down": p_attr = curses.color_pair(CP_BLUE);   needle = ["  .---.", " ( <-- )", "'-------'"]
            else:                p_attr = curses.color_pair(CP_DIM);    needle = ["  .---.", " (  -  )", "'-------'"]

            sign     = "+" if change >= 0 else ""
            desc_map = {
                "up":   "Fair likely" if change < 3 else "Clearing",
                "flat": "Stable",
                "down": "Change likely" if change > -3 else "Storm possible",
            }
            desc = desc_map[dirn]

            ws(win, box_top + 3,  pres_x, "PRESSURE", curses.color_pair(CP_DIM))
            for i, line in enumerate(needle):
                ws(win, box_top + 5 + i, pres_x, line, p_attr | curses.A_BOLD)
            ws(win, box_top + 9,  pres_x, f"{hpa} hPa", p_attr | curses.A_BOLD)
            ws(win, box_top + 10, pres_x, trend, p_attr)
            ws(win, box_top + 11, pres_x, f"{sign}{change} hPa/3h", curses.color_pair(CP_DIM))
            ws(win, box_top + 12, pres_x, desc, curses.color_pair(CP_DIM))

    # ── Bottom status bar ─────────────────────────────────────────────────────
    if h > 2:
        ws(win, h - 2, 0, "-" * (w - 1), curses.color_pair(CP_DIM))
        if status_msg:
            bar = f"  ! {status_msg[:w - 4]} "
        else:
            bar = (f"  Updated {last_updated}"
                   f"  |  Refresh {REFRESH_SECONDS}s"
                   f"  |  [r] refresh  [a] analog  [d] digital  [q] quit  ")
        ws(win, h - 1, 0, bar[:w - 1], curses.color_pair(CP_DIM))

    win.refresh()




# ─── Analog clock ─────────────────────────────────────────────────────────────

def draw_clock(win, origin_row, origin_col, now):
    """Draw an ASCII analog clock face at (origin_row, origin_col).

    Clock is 21 chars wide x 11 rows tall (accounts for 2:1 char aspect ratio).
    Hour, minute and second hands computed from current time.
    Runs independently — called every frame, reads datetime.now() directly.
    """
    import math

    CW = 21    # clock canvas width  (chars)
    CH = 11    # clock canvas height (rows)
    # Effective radius in character-space. Because chars are ~2x taller than
    # wide we scale y by 0.5 when computing the circle so it looks round.
    RX = 9.5   # x-radius in chars
    RY = 4.8   # y-radius in rows (≈ RX * 0.5 for 2:1 aspect)
    cx = CW // 2
    cy = CH // 2

    # Angle helper — 0 = 12 o'clock, clockwise, returns (dx, dy) in char-space
    def hand_char(angle_deg):
        """Pick the best ASCII character for a given hand angle."""
        a = angle_deg % 180
        if a < 22.5 or a >= 157.5:  return '|'
        if a < 67.5:                 return '\\'
        if a < 112.5:                return '-'
        return '/'

    def plot_hand(grid, length_x, length_y, angle_deg, char, attr_key):
        """Step along a hand from centre outward, placing characters."""
        rad = math.radians(angle_deg - 90)   # -90 so 0° = up
        for step in range(1, int(max(length_x, length_y)) + 1):
            t   = step / max(length_x, length_y)
            col = cx + round(math.cos(rad) * length_x * t)
            row = cy + round(math.sin(rad) * length_y * t)
            if 0 <= row < CH and 0 <= col < CW:
                grid[row][col] = (char, attr_key)

    # Build blank grid
    grid = [[(' ', 'dim')] * CW for _ in range(CH)]

    # Clock face — ellipse outline + 12/3/6/9 tick marks
    for deg in range(0, 360, 3):
        rad = math.radians(deg)
        col = cx + round(math.cos(rad) * RX)
        row = cy + round(math.sin(rad) * RY)
        if 0 <= row < CH and 0 <= col < CW:
            grid[row][col] = ('.', 'dim')

    # Cardinal ticks
    for deg, ch in [(0, '|'), (90, '-'), (180, '|'), (270, '-')]:
        rad = math.radians(deg)
        col = cx + round(math.cos(rad) * RX)
        row = cy + round(math.sin(rad) * RY)
        if 0 <= row < CH and 0 <= col < CW:
            grid[row][col] = (ch, 'white')

    # Hour markers at 1,2,4,5,7,8,10,11
    for h12 in range(1, 13):
        deg = h12 * 30
        rad = math.radians(deg - 90)
        col = cx + round(math.cos(rad) * (RX - 1.2))
        row = cy + round(math.sin(rad) * (RY - 0.6))
        if 0 <= row < CH and 0 <= col < CW:
            grid[row][col] = ('+', 'dim')

    # Compute hand angles
    h   = now.hour % 12
    m   = now.minute
    s   = now.second
    hour_angle   = h * 30 + m * 0.5          # 30° per hour + drift
    minute_angle = m * 6 + s * 0.1           # 6° per minute + drift
    second_angle = s * 6                      # 6° per second

    # Draw hands — second, minute, hour (hour drawn last = on top)
    plot_hand(grid, RX * 0.85, RY * 0.85, second_angle,
              hand_char(second_angle), 'cyan')
    plot_hand(grid, RX * 0.75, RY * 0.75, minute_angle,
              hand_char(minute_angle), 'white')
    plot_hand(grid, RX * 0.5,  RY * 0.5,  hour_angle,
              hand_char(hour_angle),   'yellow')

    # Centre dot
    grid[cy][cx] = ('o', 'yellow')

    # Render grid to screen
    attr_map = {
        'dim':    curses.color_pair(CP_DIM),
        'white':  curses.color_pair(CP_WHITE)  | curses.A_BOLD,
        'yellow': curses.color_pair(CP_YELLOW) | curses.A_BOLD,
        'cyan':   curses.color_pair(CP_CYAN)   | curses.A_BOLD,
    }
    for r, row_cells in enumerate(grid):
        for c, (ch, attr_key) in enumerate(row_cells):
            ws(win, origin_row + r, origin_col + c, ch, attr_map[attr_key])


def draw_clock_fullscreen(win, now, use_ampm=False):
    """Full screen analog clock — scaled to fill the terminal."""
    import math
    h, w = win.getmaxyx()
    win.erase()

    # Scale clock to half screen width, preserving 2:1 char aspect ratio
    RX = w // 4 - 2
    RY = int(RX * 0.48)
    CW = w
    CH = min(h - 4, RY * 2 + 3)
    cx = CW // 2
    cy = CH // 2

    def hand_char(angle_deg):
        a = angle_deg % 180
        if a < 22.5 or a >= 157.5: return '|'
        if a < 67.5:                return '\\'
        if a < 112.5:               return '-'
        return '/'

    def plot_hand(grid, lx, ly, angle_deg, char, attr_key):
        rad = math.radians(angle_deg - 90)
        for step in range(1, int(max(lx, ly)) + 1):
            t   = step / max(lx, ly)
            col = cx + round(math.cos(rad) * lx * t)
            row = cy + round(math.sin(rad) * ly * t)
            if 0 <= row < CH and 0 <= col < CW:
                grid[row][col] = (char, attr_key)

    grid = [[(' ', 'dim')] * CW for _ in range(CH)]

    # Clock face ellipse
    for deg in range(0, 360, 2):
        rad = math.radians(deg)
        col = cx + round(math.cos(rad) * RX)
        row = cy + round(math.sin(rad) * RY)
        if 0 <= row < CH and 0 <= col < CW:
            grid[row][col] = ('.', 'dim')

    # Cardinal ticks
    for deg, ch in [(0,'|'),(90,'-'),(180,'|'),(270,'-')]:
        rad = math.radians(deg)
        col = cx + round(math.cos(rad) * RX)
        row = cy + round(math.sin(rad) * RY)
        if 0 <= row < CH and 0 <= col < CW:
            grid[row][col] = (ch, 'white')

    # Hour markers
    for h12 in range(1, 13):
        rad = math.radians(h12 * 30 - 90)
        col = cx + round(math.cos(rad) * (RX - 2))
        row = cy + round(math.sin(rad) * (RY - 1))
        if 0 <= row < CH and 0 <= col < CW:
            grid[row][col] = ('+', 'dim')

    # Hands
    hh = now.hour % 12
    m  = now.minute
    s  = now.second
    plot_hand(grid, RX*0.85, RY*0.85, s*6,               hand_char(s*6),               'cyan')
    plot_hand(grid, RX*0.75, RY*0.75, m*6 + s*0.1,       hand_char(m*6),               'white')
    plot_hand(grid, RX*0.5,  RY*0.5,  hh*30 + m*0.5,     hand_char(hh*30 + m*0.5),    'yellow')
    grid[cy][cx] = ('o', 'yellow')

    attr_map = {
        'dim':    curses.color_pair(CP_DIM),
        'white':  curses.color_pair(CP_WHITE)  | curses.A_BOLD,
        'yellow': curses.color_pair(CP_YELLOW) | curses.A_BOLD,
        'cyan':   curses.color_pair(CP_CYAN)   | curses.A_BOLD,
    }
    for r, row_cells in enumerate(grid):
        for c, (ch, attr_key) in enumerate(row_cells):
            ws(win, r, c, ch, attr_map[attr_key])

    # Date and time centered below clock
    date_str = now.strftime("%A  %B %-d  %Y").upper()
    time_str = now.strftime("%I:%M:%S %p") if use_ampm else now.strftime("%H:%M:%S")
    date_row = CH + 1
    time_row = CH + 2
    if date_row < h:
        ws(win, date_row, (w - len(date_str)) // 2, date_str,
           curses.color_pair(CP_WHITE) | curses.A_BOLD)
    if time_row < h:
        ws(win, time_row, (w - len(time_str)) // 2, time_str,
           curses.color_pair(CP_DIM))
    win.refresh()


def draw_digital_fullscreen(win, now, use_ampm=False):
    """Full screen digital clock — big digit art, HH:MM, date below."""
    h, w = win.getmaxyx()
    win.erase()

    # Larger 7-row glyphs
    _BIG = {
        '0': [' _______ ', '|       |', '|       |', '|       |', '|       |', '|       |', '|       |', '|       |', '|       |', '|_______|'],
        '1': ['         ', '     |   ', '     |   ', '     |   ', '     |   ', '     |   ', '     |   ', '     |   ', '     |   ', '     |   '],
        '2': [' _____   ', '      |  ', '      |  ', '      |  ', ' _____|  ', '|        ', '|        ', '|        ', '|        ', '|_____   '],
        '3': [' ______  ', '       | ', '       | ', '       | ', '  -----| ', '       | ', '       | ', '       | ', '       | ', ' ______| '],
        '4': ['|      | ', '|      | ', '|      | ', '|______| ', '       | ', '       | ', '       | ', '       | ', '       | ', '       | '],
        '5': [' ______  ', '|        ', '|        ', '|        ', '|______  ', '       | ', '       | ', '       | ', '       | ', ' ______| '],
        '6': [' ______  ', '|        ', '|        ', '|        ', '|______  ', '|      | ', '|      | ', '|      | ', '|      | ', '|______| '],
        '7': [' ______  ', '       | ', '       | ', '       | ', '       | ', '       | ', '       | ', '       | ', '       | ', '       | '],
        '8': [' _______ ', '|       |', '|       |', '|       |', '|_______|', '|       |', '|       |', '|       |', '|       |', '|_______|'],
        '9': [' ______  ', '|      | ', '|      | ', '|______| ', '       | ', '       | ', '       | ', '       | ', '       | ', ' ______| '],
        ':': ['         ', '         ', '   ██    ', '         ', '         ', '         ', '         ', '   ██    ', '         ', '         '],
        ' ': ['         ', '         ', '         ', '         ', '         ', '         ', '         ', '         ', '         ', '         '],
    }

    # HH:MM only — no seconds
    if use_ampm:
        time_str = now.strftime("%I:%M")
        time_str = time_str.lstrip('0') or '0'
        ampm     = now.strftime(" %p")
    else:
        time_str = now.strftime("%H:%M")
        ampm     = ""

    rows = [''] * 10
    for ch in time_str:
        g = _BIG.get(ch, _BIG[' '])
        for i in range(10):
            rows[i] += g[i] + ' '

    dig_w    = max(len(r) for r in rows)
    dig_h    = 10
    start_col = max(0, (w - dig_w) // 2)
    start_row = max(0, (h - dig_h - 4) // 2)

    for i, r in enumerate(rows):
        ws(win, start_row + i, start_col, r[:w - 1],
           curses.color_pair(CP_YELLOW) | curses.A_BOLD)

    if ampm:
        ws(win, start_row, start_col + dig_w + 1, ampm,
           curses.color_pair(CP_DIM))

    # Date centered below digits
    date_str = now.strftime("%A  %B %-d  %Y").upper()
    date_row = start_row + dig_h + 2
    if date_row < h:
        ws(win, date_row, (w - len(date_str)) // 2, date_str,
           curses.color_pair(CP_WHITE) | curses.A_BOLD)

    win.refresh()


# ─── Main curses loop ─────────────────────────────────────────────────────────

def draw_loading(win, message, is_error=False):
    win.erase()
    h, w = win.getmaxyx()
    attr = curses.color_pair(CP_RED if is_error else CP_CYAN) | curses.A_BOLD
    ws(win, h // 2, max(0, (w - len(message)) // 2), message, attr)
    spinner = r"-\|/"
    ws(win, h // 2 + 1, w // 2,
       spinner[int(time.time() * 4) % 4],
       curses.color_pair(CP_YELLOW))
    win.refresh()


def main(stdscr, location_arg, country, force_latin=False):
    curses.curs_set(0)
    stdscr.nodelay(True)
    init_colors()

    weather      = None
    location     = location_arg
    lat = lon    = None
    last_fetch   = 0.0
    last_updated = "--:--:--"
    frame_idx    = 0
    status_msg   = ""
    frame_delay  = 1.0 / ANIMATE_FPS
    next_frame   = time.time()
    clock_mode   = None   # None | 'analog' | 'digital'

    while True:
        now = time.time()

        # ── Re-fetch if stale ─────────────────────────────────────────────────
        if weather is None or now - last_fetch >= REFRESH_SECONDS:
            draw_loading(stdscr, f"  Looking up {location_arg}...  ")
            try:
                if lat is None:
                    lat, lon, location, cc = location_to_coords(location_arg, country, force_latin=force_latin)
                    # Auto-switch to metric if user didn't explicitly set units
                    # and the resolved country is metric
                    global TEMP_UNIT, WIND_UNIT
                    if cc in METRIC_COUNTRIES:
                        if TEMP_UNIT == "fahrenheit" and not _units_explicit:
                            TEMP_UNIT = "celsius"
                        if WIND_UNIT == "mph" and not _wind_explicit:
                            WIND_UNIT = "kmh"
                draw_loading(stdscr, f"  Fetching weather for {location}...  ")
                weather           = parse_weather(fetch_weather(lat, lon))
                weather["cc"]     = cc
                weather["aqi"]    = fetch_aqi(lat, lon)
                last_fetch   = now
                last_updated = datetime.now().strftime("%H:%M:%S")
                status_msg   = ""
            except Exception as exc:
                status_msg = str(exc)[:70]
                if weather is None:
                    draw_loading(stdscr, f"  Error: {status_msg}  ", is_error=True)
                    time.sleep(5)
                    last_fetch = now - REFRESH_SECONDS + 30
                    continue

        # ── Draw ──────────────────────────────────────────────────────────────
        if now >= next_frame:
            AMPM_COUNTRIES = {"us","ca","au","nz","ph","eg","sa","pk","in"}
            _cc = (weather or {}).get("cc", DEFAULT_COUNTRY or "us").lower()
            use_ampm = _cc in AMPM_COUNTRIES
            if clock_mode == 'analog':
                draw_clock_fullscreen(stdscr, datetime.now(), use_ampm)
            elif clock_mode == 'digital':
                draw_digital_fullscreen(stdscr, datetime.now(), use_ampm)
            elif weather is not None:
                draw_frame(stdscr, weather, location,
                           frame_idx, last_updated, status_msg)
            frame_idx  += 1
            next_frame += frame_delay

        # ── Input ─────────────────────────────────────────────────────────────
        key = stdscr.getch()
        if key in (ord('q'), ord('Q'), 27):
            break
        if key in (ord('r'), ord('R')):
            last_fetch = 0
        if key in (ord('a'), ord('A')):
            clock_mode = None if clock_mode == 'analog' else 'analog'
            stdscr.clear()
        if key in (ord('d'), ord('D')):
            clock_mode = None if clock_mode == 'digital' else 'digital'
            stdscr.clear()
        if key == curses.KEY_RESIZE:
            stdscr.clear()

        # ── Sleep until next frame, max 50ms for responsive input ─────────────
        time.sleep(max(0.0, min(next_frame - time.time(), 0.05)))


# ─── Preview mode loop ────────────────────────────────────────────────────────

CONDITIONS = list(ART.keys())

def preview(stdscr, start_condition):
    """Cycle through all conditions for visual review. No network needed."""
    curses.curs_set(0)
    stdscr.nodelay(True)
    init_colors()

    # Fake weather data so the left panel renders normally
    fake_weather = {
        "temp":       "54F",
        "feels_like": "50F",
        "humidity":   "67%",
        "wind":       "12 mph NE",
        "condition":  start_condition,
        "sunrise":    "06:14",
        "sunset":     "19:47",
        "moon_name":  moon_phase()[0],
        "cc":         "us",
        "aqi":        {"aqi": 42, "cat": "Good", "col": "green", "pm25": 8.2},
        "pressure":   {"hpa": 1018.4, "change": 2.4, "trend": "Rising", "dir": "up"},
        "forecast":   [
            {"label": "3pm",  "temp": "55F", "code": 0,  "precip_pct": 4},
            {"label": "4pm",  "temp": "54F", "code": 3,  "precip_pct": 15},
            {"label": "5pm",  "temp": "52F", "code": 61, "precip_pct": 50},
            {"label": "6pm",  "temp": "50F", "code": 63, "precip_pct": 70},
            {"label": "7pm",  "temp": "49F", "code": 65, "precip_pct": 90},
        ],
    }

    cond_idx   = CONDITIONS.index(start_condition) if start_condition in CONDITIONS else 0
    frame_idx  = 0
    frame_delay = 1.0 / ANIMATE_FPS
    next_frame  = time.time()

    while True:
        now = time.time()

        fake_weather["condition"] = CONDITIONS[cond_idx]

        if now >= next_frame:
            # Status bar shows condition name and nav hints
            cond_name = CONDITIONS[cond_idx].upper()
            total     = len(CONDITIONS)
            status    = (f"  PREVIEW {cond_idx + 1}/{total}: {cond_name}"
                         f"  |  [n] next  [p] prev  [q] quit  ")
            draw_frame(stdscr, fake_weather, "PREVIEW",
                       frame_idx, "--:--:--", status)
            frame_idx += 1
            next_frame += frame_delay

        key = stdscr.getch()
        if key in (ord('q'), ord('Q'), 27):
            break
        if key in (ord('n'), ord('N'), curses.KEY_RIGHT):
            cond_idx   = (cond_idx + 1) % len(CONDITIONS)
            frame_idx  = 0
            hold_count = 0
        if key in (ord('p'), ord('P'), curses.KEY_LEFT):
            cond_idx   = (cond_idx - 1) % len(CONDITIONS)
            frame_idx  = 0
            hold_count = 0
        if key == curses.KEY_RESIZE:
            stdscr.clear()

        time.sleep(max(0.0, min(next_frame - time.time(), 0.05)))


# ─── Entry point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    ap = argparse.ArgumentParser(
        description="StormShell — terminal weather display, works worldwide",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  stormshell --location "Chicago"
  stormshell --location "60602"
  stormshell --location "London" --country gb
  stormshell --location "Tokyo" --country jp
  stormshell --kiosk --location "Chicago"
  stormshell --kiosk --location "London" --country gb
  stormshell --preview
  stormshell --preview --condition storm
        """,
    )
    ap.add_argument("--location",  default=DEFAULT_LOCATION, metavar="PLACE",
                    help="City name, ZIP code, or postal code (default: Chicago, IL)")
    ap.add_argument("--country",   default=DEFAULT_COUNTRY,  metavar="CC",
                    help="ISO 2-letter country code to narrow search: gb de fr jp au...")
    ap.add_argument("--units",     default=None,
                    choices=["fahrenheit", "celsius"],
                    help="Temperature units (default: auto by country)")
    ap.add_argument("--wind",      default=None,
                    choices=["mph", "kmh", "ms", "kn"],
                    help="Wind speed units (default: auto by country)")
    ap.add_argument("--refresh",   default=REFRESH_SECONDS, type=int, metavar="SECS")
    ap.add_argument("--sun-char",  default=SUN_CHAR, metavar="CHAR")
    ap.add_argument("--_tty_mode", action="store_true",
                    help=argparse.SUPPRESS)
    ap.add_argument("--kiosk",   action="store_true",
                    help="Send output to HDMI display (TTY1) instead of current terminal")
    ap.add_argument("--display", action="store_true",
                    help=argparse.SUPPRESS)   # legacy alias for --kiosk
    ap.add_argument("--preview",   action="store_true",
                    help="Preview all animations without fetching weather")
    ap.add_argument("--condition", default=CONDITIONS[0],
                    choices=CONDITIONS, metavar="COND",
                    help=f"Start preview on condition: {', '.join(CONDITIONS)}")
    args = ap.parse_args()

    # --display is a legacy alias for --kiosk
    if args.display:
        args.kiosk = True

    # Track whether user explicitly set units — affects auto-metric logic
    _units_explicit = args.units is not None
    _wind_explicit  = args.wind  is not None

    TEMP_UNIT       = args.units   or TEMP_UNIT
    WIND_UNIT       = args.wind    or WIND_UNIT
    REFRESH_SECONDS = args.refresh
    SUN_CHAR        = args.sun_char

    # ── Display mode — takes over HDMI TTY1, restores it on exit ─────────────
    if args.kiosk:
        # Re-launch with sudo if not already root
        if os.geteuid() != 0:
            os.execvp("sudo", ["sudo", sys.executable] + sys.argv)
            sys.exit(0)   # unreachable, execvp replaces the process

        FONT = "/usr/share/consolefonts/Uni2-TerminusBold28x14.psf.gz"
        TTY  = "/dev/tty1"

        def restore_tty():
            subprocess.run(["systemctl", "start", "getty@tty1"],
                           capture_output=True)

        atexit.register(restore_tty)
        signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))

        # Stop getty, load font, switch display to TTY1
        subprocess.run(["systemctl", "stop",  "getty@tty1"], capture_output=True)
        subprocess.run(["setfont", FONT, "-C", TTY],         capture_output=True)
        subprocess.run(["chvt", "1"],                        capture_output=True)
        # Force exact terminal dimensions to match font/resolution
        subprocess.run(["stty", "rows", "27", "cols", "97"],
                       stdin=open(TTY), capture_output=True)
        time.sleep(0.3)

        # Build child args — swap --kiosk for --_tty_mode so the child
        # goes straight to curses without repeating the TTY setup
        child_args = [a for a in sys.argv[1:] if a not in ("--kiosk", "--display")]
        # Only inject units if user explicitly passed them — otherwise let
        # auto-metric detection work based on the resolved location country
        if "--units" not in child_args and _units_explicit:
            child_args += ["--units", TEMP_UNIT]
        if "--wind" not in child_args and _wind_explicit:
            child_args += ["--wind", WIND_UNIT]
        child_args.append("--_tty_mode")

        # Run curses as a subprocess whose stdin/stdout/stderr ARE TTY1.
        # This makes TTY1 the controlling terminal from process birth —
        # curses will attach to it correctly.
        tty_fh = open(TTY, "wb", buffering=0)   # output only to TTY1
        os.environ["TERM"] = "linux"

        # Log child errors to a file so we can debug without losing them to TTY1
        errlog = "/tmp/stormshell_display.log"
        try:
            with open(errlog, "wb") as err_fh:
                result = subprocess.run(
                    [sys.executable, os.path.abspath(__file__)] + child_args,
                    stdin=None,      # inherit SSH stdin — keys come from SSH session
                    stdout=tty_fh,   # display output goes to HDMI TTY1
                    stderr=err_fh,
                )
        except KeyboardInterrupt:
            pass   # Ctrl+C — clean exit
        finally:
            tty_fh.close()

        # Show any errors back in the SSH terminal
        try:
            err = open(errlog).read().strip()
            if err and 'result' in dir() and result.returncode != 0:
                print(f"\n  Child error (returncode {result.returncode}):\n{err}\n")
        except Exception:
            pass

        restore_tty()
        print("""
  +------------------------------------------+
  |                                          |
  |    Thanks for using StormShell  ☼        |
  |    Have a nice day!                      |
  |                                          |
  +------------------------------------------+
""")

    else:
        # ── Normal / TTY child mode — runs in current terminal ────────────────
        if args._tty_mode:
            os.environ.setdefault("TERM", "linux")
        try:
            if args.preview:
                curses.wrapper(preview, args.condition)
            else:
                curses.wrapper(main, args.location, args.country, args._tty_mode)
        except KeyboardInterrupt:
            pass

        print("""
  +------------------------------------------+
  |                                          |
  |    Thanks for using StormShell  ☼        |
  |    Have a nice day!                      |
  |                                          |
  +------------------------------------------+
""")

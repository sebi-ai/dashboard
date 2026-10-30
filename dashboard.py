import itertools
import json
import math
import os
import queue
import sys
import threading
import time
from datetime import datetime
from urllib.parse import urlencode

try:
    import tkinter as tk
    import tkinter.font as tkfont
    HAS_TKINTER = True
except ImportError:
    # Headless server (no python3-tk): `streamlit run dashboard.py` still
    # imports this module for the WEB dashboard, which never touches Tk. A
    # stand-in that returns throwaway classes keeps the `class X(tk.Canvas)`
    # definitions below importable; the desktop path refuses to start without
    # real tkinter (see __main__).
    class _TkStub:
        def __getattr__(self, name):
            return type(name, (), {"__init__": lambda self, *a, **k: None})

    tk = _TkStub()
    tkfont = _TkStub()
    HAS_TKINTER = False

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

FONT_FAMILY = "Orbitron"
# Orbitron TTFs bundled with the project (same font the website loads from
# Google Fonts). The desktop (Tk) dashboard can only use fonts installed on
# the machine, so we register these as *private* GDI fonts at Tk startup:
# Windows keeps them for our process only — no global installation needed.
_BUNDLED_FONT_FILES = ("Orbitron-Regular.ttf", "Orbitron-Bold.ttf")


def register_orbitron_private():
    """Make the bundled Orbitron font usable to Tk in this process (Windows).

    AddFontResourceExW + FR_PRIVATE registers the font for this process only.
    Must be called before widgets are created (Tk resolves font families on
    first use). Callers on other platforms or with a missing fonts/ directory
    get the previous behaviour: Tk silently falls back to its default font.
    """
    if sys.platform != "win32":
        return
    fonts_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts")
    try:
        import ctypes

        FR_PRIVATE = 0x10  # load the font for this process only
        for name in _BUNDLED_FONT_FILES:
            path = os.path.join(fonts_dir, name)
            if os.path.isfile(path):
                ctypes.windll.gdi32.AddFontResourceExW(path, FR_PRIVATE, None)
    except Exception:
        pass  # cosmetic enhancement — never block startup over it


def _mask_email_display(raw):
    """Anonymise an email address for display: keep only the first character of
    the local part (e.g. "j***@example.com"). Non-email strings pass through."""
    raw = (raw or "").strip()
    at = raw.find("@")
    if at <= 0:
        return raw
    return f"{raw[0]}***@{raw[at + 1:]}"


def _mask_email_sender(raw):
    """Safe-to-display sender line for MESSAGES widgets.

    "Display Name <addr>" renders as the name only; a bare address is masked.
    No dashboard — Tk or web — ever puts a raw email address on screen.
    """
    raw = (raw or "").strip()
    if not raw:
        return "(unknown sender)"
    if raw.endswith(">") and "<" in raw:
        name, _lt, rest = raw.partition("<")
        addr = rest[: -1].strip()
        name = name.strip().strip('"').strip()
        if name:
            return name
        return _mask_email_display(addr)
    return _mask_email_display(raw)

WEATHER_CODES = {
    0: ("Clear sky", ""),
    1: ("Mainly clear", ""),
    2: ("Partly cloudy", ""),
    3: ("Overcast", ""),
    45: ("Fog", ""),
    48: ("Depositing rime fog", ""),
    51: ("Light drizzle", ""),
    53: ("Moderate drizzle", ""),
    55: ("Dense drizzle", ""),
    61: ("Slight rain", ""),
    63: ("Moderate rain", ""),
    65: ("Heavy rain", ""),
    71: ("Slight snow", ""),
    73: ("Moderate snow", ""),
    75: ("Heavy snow", ""),
    77: ("Snow grains", ""),
    80: ("Slight rain showers", ""),
    81: ("Moderate rain showers", ""),
    82: ("Violent rain showers", ""),
    85: ("Slight snow showers", ""),
    86: ("Heavy snow showers", ""),
    95: ("Thunderstorm", ""),
    96: ("Thunderstorm with hail", ""),
    99: ("Severe thunderstorm", ""),
}

THEMES = {
    "default": {
        "bg": "#0d0d1a",
        "widget_bg": "#16162a",
        "accent": "#00d4ff",
        "text": "#e0e0ff",
        "border": "#2a2a50",
        "muted": "#6666aa",
        "positive": "#00ff88",
        "negative": "#ff4466",
    },
    "ocean": {
        "bg": "#080e1a",
        "widget_bg": "#0f1e30",
        "accent": "#00b4d8",
        "text": "#caf0f8",
        "border": "#1a3050",
        "muted": "#5588aa",
        "positive": "#00e5b0",
        "negative": "#ff5555",
    },
    "forest": {
        "bg": "#080f08",
        "widget_bg": "#0f1e12",
        "accent": "#52b788",
        "text": "#d8f3dc",
        "border": "#1e3d25",
        "muted": "#558866",
        "positive": "#74c69d",
        "negative": "#ff6b6b",
    },
    "sunset": {
        "bg": "#180800",
        "widget_bg": "#261200",
        "accent": "#ff7b35",
        "text": "#ffe8d6",
        "border": "#552200",
        "muted": "#aa6644",
        "positive": "#ffbb44",
        "negative": "#ff3333",
    },
    "cyberpunk": {
        "bg": "#080010",
        "widget_bg": "#10001e",
        "accent": "#ff00ff",
        "text": "#00ffff",
        "border": "#3a0060",
        "muted": "#882288",
        "positive": "#00ff88",
        "negative": "#ff2244",
    },
    "ice": {
        "bg": "#080816",
        "widget_bg": "#12182a",
        "accent": "#90caf9",
        "text": "#e8f4ff",
        "border": "#1e2e48",
        "muted": "#4466aa",
        "positive": "#66ddff",
        "negative": "#ff6688",
    },
    "midnight": {
        "bg": "#030008",
        "widget_bg": "#0a0018",
        "accent": "#9b59b6",
        "text": "#dda0ff",
        "border": "#25004a",
        "muted": "#6a308a",
        "positive": "#a855f7",
        "negative": "#ff4488",
    },
    "light": {
        "bg": "#f4f7ff",
        "widget_bg": "#ffffff",
        "accent": "#0002c0",
        "text": "#071a4a",
        "border": "#0002c0",
        "muted": "#5d6c86",
        "positive": "#0a8f5b",
        "negative": "#d83a52",
    },
    "dark": {
        "bg": "#0b0b12",
        "widget_bg": "#16161f",
        "accent": "#8ab4f8",
        "text": "#e6e6ee",
        "border": "#2e2e42",
        "muted": "#6f6f88",
        "positive": "#00e58a",
        "negative": "#ff5566",
    },
    "pink": {
        "bg": "#1a0d14",
        "widget_bg": "#2b1221",
        "accent": "#ff66b2",
        "text": "#ffe3f0",
        "border": "#5c2040",
        "muted": "#a05a7e",
        "positive": "#00e58a",
        "negative": "#ff5566",
    },
}

# The Streamlit dashboard fetches its widget data from server.py. Both run on
# the same machine, so the loopback address works everywhere — server.py
# exports its PORT so a non-default port is picked up automatically.
SERVER_URL = os.environ.get("SERVER_URL") or f"http://127.0.0.1:{os.environ.get('PORT', '8000')}"


def _open_meteo_url(coords):
    """The open-meteo query for the configured location.

    Shared by the server-side fetch and the web widget's client-side poller:
    open-meteo allows cross-origin browser requests, so the browser polls it
    directly — no server round-trip and no Streamlit rerun involved.
    """
    lat = coords.get("lat") or coords.get("latitude") or 48.137
    lon = coords.get("lon") or coords.get("longitude") or 11.575
    query = urlencode({
        "latitude": lat,
        "longitude": lon,
        "current": (
            "temperature_2m,weathercode,"
            "windspeed_10m,apparent_temperature"
        ),
        "wind_speed_unit": "kmh",
        "timezone": "auto",
    })
    return "https://api.open-meteo.com/v1/forecast?" + query


def _fetch_open_meteo_current(coords, attempts=3, timeout=8):
    """Fetch current weather from open-meteo with brief retries.

    Transient connection resets (Wi-Fi blips, antivirus web proxies, bursty
    startup timing) used to surface raw exception text such as
    "Error: HTTPSConnectionPool(host='api.open-meteo..." in the weather
    widget. Retrying a few times with a short backoff silently absorbs those
    blips. Returns the parsed fields as a dict; raises the last
    ``requests.exceptions.RequestException`` when every attempt fails, so the
    caller decides how to present the outage.
    """
    last_exc = None
    for attempt in range(attempts):
        try:
            r = requests.get(_open_meteo_url(coords), timeout=timeout)
            r.raise_for_status()
            cur = r.json().get("current", {})
            desc, icon = WEATHER_CODES.get(cur.get("weathercode", 0), ("Unknown", "?"))
            return {
                "temp": cur.get("temperature_2m", "--"),
                "feels": cur.get("apparent_temperature", "--"),
                "desc": desc,
                "icon": icon,
                "wind": cur.get("windspeed_10m", "--"),
            }
        except requests.exceptions.RequestException as exc:
            last_exc = exc
            if attempt < attempts - 1:
                time.sleep(0.8 * (attempt + 1))
    raise last_exc


def settings_file_path() -> str:
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "settings.json")


def load_settings() -> dict:
    path = settings_file_path()
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"[dashboard] settings.json load error: {e}")
    return {}


def settings_file_mtime():
    """Modification time of settings.json, or None if it does not exist yet."""
    try:
        return os.path.getmtime(settings_file_path())
    except OSError:
        return None


def extract_colors(settings: dict) -> dict:
    theme_name = settings.get("theme", "default")
    theme_mode = settings.get("themeMode")

    # Wenn Custom Color oder Website Theme Mode aktiviert ist:
    # Erstelle ein dynamisches Theme basierend auf der ausgewählten Farbe
    custom_color = settings.get("customColor")
    preset_theme = settings.get("theme")

    if theme_mode == "custom" and custom_color:
        # Benutzerdefinierte Farbe - generiere komplett neues Farbschema
        # NUTZE NUR DIE CUSTOM COLOR für alle Elemente
        base = generate_theme_from_color(custom_color)
    elif theme_mode == "preset" and preset_theme:
        # Preset Theme aus der Website - mappe auf Dashboard-Themes
        theme_mapping = {
            "light": "light",    # Helles Theme
            "dark": "dark",      # Dunkles Theme
            "blue": "default",   # Blau (Standard)
            "green": "forest",   # Grün
            "red": "sunset",     # Rot/Orange
            "pink": "pink",      # Pink/Magenta
            "purple": "midnight",# Lila
        }
        theme_key = theme_mapping.get(preset_theme)
        if theme_key is None and preset_theme in THEMES:
            theme_key = preset_theme  # legacy saves may store a dashboard theme name
        base = THEMES.get(theme_key or "default", THEMES["default"]).copy()

        # Falls customColor zusätzlich gesetzt ist, überschreibe accent/border
        if custom_color and isinstance(custom_color, str) and custom_color.startswith("#"):
            base["accent"] = custom_color
            base["border"] = custom_color
    else:
        # Standardverhalten: Nutze Dashboard-Themes
        base = THEMES.get(theme_name, THEMES["default"]).copy()

    # Manuelle Überschreibungen aus settings.json (für Rückwärtskompatibilität)
    # ABER: Nur anwenden, wenn NICHT im Custom Mode ist
    # (Im Custom Mode soll die generierte Farbe Vorrang haben)
    if theme_mode != "custom" or not custom_color:
        overrides = {
            "accent": (
                settings.get("accentColor")
                or settings.get("primaryColor")
                or settings.get("customColor")
                or settings.get("themeColor")
            ),
            "bg": (
                settings.get("backgroundColor")
                or settings.get("bgColor")
            ),
            "text": settings.get("textColor"),
            "widget_bg": (
                settings.get("widgetBgColor")
                or settings.get("cardColor")
                or settings.get("cardBgColor")
            ),
            "border": settings.get("borderColor"),
            "muted": settings.get("secondaryTextColor") or settings.get("mutedColor"),
        }
        for key, val in overrides.items():
            if val and isinstance(val, str) and val.startswith("#"):
                base[key] = val

    return base


def generate_theme_from_color(hex_color: str) -> dict:
    """
    Generiert ein vollständiges Farbschema aus einer einzelnen Hauptfarbe
    mit MAXIMALEM KONTRAST für alle Elemente (Linien, Rahmen, Text, Widgets).

    Optimierte Farbstrategie:
    - bg: Dunkle Version (V ~18-22%) - nicht zu dunkel für Widget-Kontrast
    - widget_bg: Deutlich hellere Variante (V ~35-45%) - gut sichtbar auf bg
    - accent: Die Hauptfarbe in mittlerer/heller Variante (V ~70-85%)
    - border: SEHR HELL (V >= 85%) fast weiß mit leichtem Farbstich
    - text: REINWEISS (#ffffff) für maximalen Kontrast
    - muted: Mittelhell (V ~55-65%) mit sehr geringer Sättigung

    Alle Kontraste sind optimiert für:
    - border vs widget_bg >= 3:1 (gute Rahmensichtbarkeit)
    - border vs bg >= 4:1 (gute Sichtbarkeit auf Hintergrund)
    - widget_bg vs bg >= 2:1 (Widgets heben sich ab)
    - text vs widget_bg >= 15:1 (perfekte Lesbarkeit)
    - accent vs widget_bg >= 4.5:1 (Icons/Überschriften gut sichtbar)
    """
    import colorsys

    # Entferne # und konvertiere zu RGB (0-255)
    hex_color = hex_color.lstrip("#")
    if len(hex_color) == 3:
        r, g, b = int(hex_color[0]*2, 16), int(hex_color[1]*2, 16), int(hex_color[2]*2, 16)
    else:
        r, g, b = int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)

    # Normalisiere zu 0-1 für colorsys
    r_norm, g_norm, b_norm = r/255.0, g/255.0, b/255.0

    # Konvertiere zu HSV für einfache Anpassungen
    h, s, v = colorsys.rgb_to_hsv(r_norm, g_norm, b_norm)

    # --- Hintergrundfarben ---
    # bg: Dunkel aber nicht zu dunkel (V ~18-22%)
    # damit Widgets (V ~35-45%) guten Kontrast haben
    bg_v = max(0.12, min(0.22, v * 0.3))
    bg_s = min(0.8, s * 1.2)
    bg_r, bg_g, bg_b = colorsys.hsv_to_rgb(h, bg_s, bg_v)
    bg_hex = rgb_to_hex(int(bg_r*255), int(bg_g*255), int(bg_b*255))

    # widget_bg: DEUTLICH HELLER als bg (V ~35-45%) damit Widgets sichtbar sind
    # Kontrast zu bg sollte >= 2:1 sein
    widget_v = min(0.45, max(0.30, bg_v * 2.0))
    widget_s = bg_s
    widget_r, widget_g, widget_b = colorsys.hsv_to_rgb(h, widget_s, widget_v)
    widget_hex = rgb_to_hex(int(widget_r*255), int(widget_g*255), int(widget_b*255))

    # --- Akzentfarbe (für Icons, Überschriften) ---
    # accent: Die Hauptfarbe, deutlich aufgehellt für guten Kontrast zu widget_bg
    # Sollte einen Kontrast >= 4.5:1 zu widget_bg haben
    accent_v = min(0.85, v * 1.5)
    accent_s = min(0.95, s * 1.1)
    accent_r, accent_g, accent_b = colorsys.hsv_to_rgb(h, accent_s, accent_v)
    accent_hex = rgb_to_hex(int(accent_r*255), int(accent_g*255), int(accent_b*255))

    # --- Rahmen/Farben (MAXIMALER KONTRAST) ---
    # border: SEHR HELL (V >= 0.85) für maximale Sichtbarkeit
    # Fast reinweiß mit leichtem Farbstich der Hauptfarbe
    # Kontrast zu widget_bg und bg sollte >= 4:1 sein
    border_v = 0.90  # Fast Weiß
    border_s = min(0.3, s * 0.5)  # Sehr geringe Sättigung für fast neutralen Look
    border_r, border_g, border_b = colorsys.hsv_to_rgb(h, border_s, border_v)
    border_hex = rgb_to_hex(int(border_r*255), int(border_g*255), int(border_b*255))

    # --- Textfarben ---
    # text: REINWEISS für besten Kontrast zum dunklen Hintergrund
    text_hex = "#ffffff"

    # muted: Mittelhell (V ~0.55-0.65) mit sehr geringer Sättigung
    muted_v = 0.60
    muted_s = max(0.05, s * 0.1)
    muted_r, muted_g, muted_b = colorsys.hsv_to_rgb(h, muted_s, muted_v)
    muted_hex = rgb_to_hex(int(muted_r*255), int(muted_g*255), int(muted_b*255))

    # --- Positive/Negative Farben (für Kursänderungen) ---
    # positive: Hellgrün (gut sichtbar)
    pos_h = 120/360
    pos_r, pos_g, pos_b = colorsys.hsv_to_rgb(pos_h, 0.8, 0.9)
    positive_hex = rgb_to_hex(int(pos_r*255), int(pos_g*255), int(pos_b*255))

    # negative: Hellrot (gut sichtbar)
    neg_h = 0/360
    neg_r, neg_g, neg_b = colorsys.hsv_to_rgb(neg_h, 0.8, 0.9)
    negative_hex = rgb_to_hex(int(neg_r*255), int(neg_g*255), int(neg_b*255))

    return {
        "bg": bg_hex,
        "widget_bg": widget_hex,
        "accent": accent_hex,
        "text": text_hex,
        "border": border_hex,
        "muted": muted_hex,
        "positive": positive_hex,
        "negative": negative_hex,
    }


def rgb_to_hex(r: int, g: int, b: int) -> str:
    """Konvertiert RGB (0-255) zu Hex-Code (#RRGGBB)"""
    return f"#{r:02x}{g:02x}{b:02x}"


def hex_to_luminance(hex_color: str) -> float:
    """Berechnet die relative Luminanz einer Farbe (0-1) nach WCAG"""
    hex_color = hex_color.lstrip("#")
    if len(hex_color) == 3:
        r, g, b = int(hex_color[0]*2, 16), int(hex_color[1]*2, 16), int(hex_color[2]*2, 16)
    else:
        r, g, b = int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)

    # Normalisiere zu 0-1
    r_norm = r / 255.0
    g_norm = g / 255.0
    b_norm = b / 255.0

    # Gamma-Korrektur für sRGB
    r_srgb = r_norm / 12.92 if r_norm <= 0.03928 else ((r_norm + 0.055) / 1.055) ** 2.4
    g_srgb = g_norm / 12.92 if g_norm <= 0.03928 else ((g_norm + 0.055) / 1.055) ** 2.4
    b_srgb = b_norm / 12.92 if b_norm <= 0.03928 else ((b_norm + 0.055) / 1.055) ** 2.4

    # Luminanz berechnen (WCAG Formel)
    luminance = 0.2126 * r_srgb + 0.7152 * g_srgb + 0.0722 * b_srgb
    return luminance


def get_contrast_ratio(color1: str, color2: str) -> float:
    """Berechnet das Kontrastverhältnis zwischen zwei Farben (WCAG)"""
    l1 = hex_to_luminance(color1)
    l2 = hex_to_luminance(color2)

    # Die hellere Farbe durch die dunklere teilen
    lighter = max(l1, l2)
    darker = min(l1, l2)

    if darker == 0:
        return float('inf')

    return (lighter + 0.05) / (darker + 0.05)


def get_contrast_aware_text_color(bg_color: str, preferred_color: str) -> str:
    """
    Gibt die Textfarbe zurück, die guten Kontrast zum Hintergrund hat.
    Bevorzugt die preferred_color, aber wenn der Kontrast zu schlecht ist,
    verwendet es stattdessen weiß oder schwarz.

    Mindestkontrast: 4.5:1 (WCAG AA für normale Texte)
    """
    # Bevorzugte Farbe testen
    ratio_preferred = get_contrast_ratio(preferred_color, bg_color)

    # Mindestkontrast für gute Lesbarkeit (WCAG AA)
    MIN_CONTRAST = 4.5

    if ratio_preferred >= MIN_CONTRAST:
        return preferred_color

    # versuche reinweiss
    ratio_white = get_contrast_ratio("#ffffff", bg_color)
    if ratio_white >= MIN_CONTRAST:
        return "#ffffff"

    # versuche schwarz
    ratio_black = get_contrast_ratio("#000000", bg_color)
    if ratio_black >= MIN_CONTRAST:
        return "#000000"

    # wenn beides zu schlecht ist, nimm die farbe mit dem besseren kontrast
    if ratio_white >= ratio_black:
        return "#ffffff"
    else:
        return "#000000"


def run_in_thread(func, *args, daemon=True):
    t = threading.Thread(target=func, args=args, daemon=daemon)
    t.start()
    return t


class RoundedBackground(tk.Canvas):
    """A canvas that draws a rounded rectangle background behind its parent frame."""
    def __init__(self, parent, bg, border_color, radius=15, **kwargs):
        # The canvas itself is painted with the PARENT's background color so
        # the area outside the rounded rectangle blends into the page, and
        # nothing white ever shows through at the corners.
        super().__init__(parent, bg=parent.cget("bg"), highlightthickness=0, **kwargs)
        self.bg = bg
        self.border_color = border_color
        self.radius = radius
        self.bind("<Configure>", self.on_configure)
        # Make sure this canvas is below the content frame.
        # NOTE: tk.Canvas aliases `lower` to `tag_lower` (a canvas-item
        # operation that needs a tag/id), so we must invoke the widget
        # stacking-order lower via the raw tk command instead.
        self.tk.call("lower", self._w)

    def on_configure(self, event):
        self.draw_rounded_rect()

    def draw_rounded_rect(self):
        self.delete("all")
        width = self.winfo_width()
        height = self.winfo_height()
        radius = self.radius

        if width <= 0 or height <= 0:
            return

        self.create_rounded_rectangle(
            0, 0, width, height,
            radius=radius,
            fill=self.bg,
            outline=self.border_color,
            width=1
        )

    def create_rounded_rectangle(self, x1, y1, x2, y2, radius, **kwargs):
        """Create a rounded rectangle on the canvas."""
        fill = kwargs.pop('fill', None)
        outline = kwargs.pop('outline', None)
        linewidth = kwargs.pop('width', 1)

        # Clamp radius to half the smaller dimension
        diameter = 2 * radius
        if x2 - x1 < diameter:
            radius = max((x2 - x1) // 2, 0)
        if y2 - y1 < diameter:
            radius = max((y2 - y1) // 2, 0)

        # Fill: a polygon sampled along the same outline as the border but
        # inset by half the border width. If it were drawn on the exact same
        # path, the border stroke's inner half would be covered by the fill and
        # the outline would look thin / as if it "points into the box" at the
        # corners. The half-width inset leaves room for the full border.
        if fill:
            inset = max(linewidth / 2.0, 0.5)
            self.create_polygon(
                self._rounded_rect_points(
                    x1 + inset, y1 + inset, x2 - inset, y2 - inset,
                    max(radius - inset, 0),
                ),
                fill=fill,
                outline="",
            )

        # Border
        if outline and linewidth > 0:
            self._draw_rounded_border(x1, y1, x2, y2, radius, outline, linewidth)

    def _rounded_rect_points(self, x1, y1, x2, y2, r):
        """Sample the rounded-rect outline (lines + quarter arcs) as polygon points."""
        if r <= 0:
            return [x1, y1, x2, y1, x2, y2, x1, y2]

        pts = [x1 + r, y1, x2 - r, y1]                     # top edge
        pts += self._arc_points(x2 - r, y1 + r, 270, 360, r)  # top-right corner
        pts += [x2, y1 + r, x2, y2 - r]                    # right edge
        pts += self._arc_points(x2 - r, y2 - r, 0, 90, r)  # bottom-right corner
        pts += [x2 - r, y2, x1 + r, y2]                    # bottom edge
        pts += self._arc_points(x1 + r, y2 - r, 90, 180, r)  # bottom-left corner
        pts += [x1, y2 - r, x1, y1 + r]                    # left edge
        pts += self._arc_points(x1 + r, y1 + r, 180, 270, r)  # top-left corner
        return pts

    def _arc_points(self, cx, cy, start_deg, end_deg, r, steps=8):
        """Points along a quarter arc using the same angle convention as create_arc."""
        pts = []
        for i in range(steps + 1):
            angle = math.radians(start_deg + (end_deg - start_deg) * i / steps)
            pts.append(cx + r * math.cos(angle))
            pts.append(cy + r * math.sin(angle))
        return pts

    def _draw_rounded_border(self, x1, y1, x2, y2, r, color, width):
        """Draw the rounded-rect border as one continuous outline polygon.

        (create_arc with style=ARC does not render reliably on some Tk/Windows
        builds, which left the corners looking like two straight lines meeting
        at a wrong angle. A single closed polygon draws the full rounded path,
        corners included, in one stroke.)
        """
        self.create_polygon(
            self._rounded_rect_points(x1, y1, x2, y2, r),
            fill="",
            outline=color,
            width=width,
        )


class BaseWidget:
    REFRESH_INTERVAL = 60

    def __init__(self, parent: tk.Frame, colors: dict, big: bool = False, settings: dict = None, scale: float = 1.0, card_h_px: float = None):
        self.parent = parent
        self.colors = colors
        self.big = big
        self.settings = settings or {}
        self.scale = max(scale, 0.5)
        self.card_h_px = card_h_px  # card height in px, used by list widgets
        self._alive = True

        # Create a container frame. NOTE: it is NOT packed here anymore — the
        # Dashboard places it with the grid manager according to the user's
        # custom layout (widgetLayout). Only enabled widgets get a container,
        # so disabled widgets simply don't exist on screen.
        self.container_frame = tk.Frame(parent, bg=parent.cget("bg"))
        self.container_frame.grid_rowconfigure(0, weight=1)
        self.container_frame.grid_columnconfigure(0, weight=1)

        # Thread-safe UI updates: worker threads post callables here and the
        # main thread drains them, so Tk widgets are never touched off-thread.
        self._ui_queue = queue.Queue()

        # Rounded background canvas fills the whole container. The content
        # frame is stacked ON TOP of it in the same grid cell (not packed
        # below it): packing both with expand=True makes the canvas swallow
        # the container and squish the content into a thin strip at the
        # bottom, which is what made widgets look "empty".
        self.bg_canvas = RoundedBackground(
            self.container_frame,
            bg=colors["widget_bg"],
            border_color=colors["border"],
            radius=30,
        )
        self.bg_canvas.grid(row=0, column=0, sticky="nsew")

        # Content frame on top of the canvas, inset so the rounded border shows.
        self.inner = tk.Frame(self.container_frame, bg=colors["widget_bg"])
        self.inner.grid(row=0, column=0, sticky="nsew", padx=18, pady=12)
        self.inner.tk.call("raise", self.inner._w)

        self.build()
        self._drain_ui()
        self._schedule_refresh()

    def ui(self, fn):
        """Run `fn` on the Tk main thread. Safe to call from any thread."""
        self._ui_queue.put(fn)

    def _drain_ui(self):
        """Main-thread loop that executes callbacks posted by worker threads."""
        try:
            while True:
                fn = self._ui_queue.get_nowait()
                try:
                    fn()
                except Exception as exc:
                    print(f"[{self.__class__.__name__}] UI update error: {exc}")
        except queue.Empty:
            pass
        if self._alive:
            try:
                self.container_frame.after(80, self._drain_ui)
            except tk.TclError:
                pass  # widget was destroyed between the check and the schedule

    def header(self, title: str):
        h = tk.Frame(self.inner, bg=self.colors["widget_bg"])
        h.pack(fill="x", pady=(0, 8))

        # Kontrastbewusste Textfarbe für Header
        widget_bg = self.colors["widget_bg"]
        accent_color = self.colors["accent"]
        header_text_color = get_contrast_aware_text_color(widget_bg, accent_color)

        # Kontrastbewusste Textfarbe für Header
        widget_bg = self.colors["widget_bg"]
        accent_color = self.colors["accent"]
        header_text_color = get_contrast_aware_text_color(widget_bg, accent_color)

        tk.Label(
            h,
            text=title,
            font=(FONT_FAMILY, self.fs(12), "bold"),
            bg=widget_bg,
            fg=header_text_color,
        ).pack(side="left")

        # Short accent underline instead of a full-width dim line — reads as a
        # modern "active tab" marker.
        tk.Frame(self.inner, height=2, width=72, bg=accent_color).pack(anchor="w", pady=(0, 10))

    def label(self, parent, text="", font_size=12, bold=False, color_key="text", anchor="center") -> tk.Label:
        weight = "bold" if bold else "normal"
        lbl = tk.Label(
            parent,
            text=text,
            font=(FONT_FAMILY, font_size, weight),
            bg=self.colors["widget_bg"],
            fg=self.colors[color_key],
            anchor=anchor,
        )
        lbl.pack(fill="x" if anchor == "w" else None)
        return lbl

    def muted_label(self, parent, text="", font_size=10, anchor="center") -> tk.Label:
        lbl = tk.Label(
            parent,
            text=text,
            font=(FONT_FAMILY, font_size),
            bg=self.colors["widget_bg"],
            fg=self.colors["muted"],
            anchor=anchor,
        )
        lbl.pack(fill="x" if anchor == "w" else None)
        return lbl

    def build(self):
        pass

    def fs(self, size: int) -> int:
        """Scale a font size to the widget's on-screen footprint, so big cards
        get big content instead of leaving 3/4 of the card empty."""
        return max(int(size * self.scale), 8)

    def fetch_data(self):
        pass

    def _schedule_refresh(self):
        if not HAS_REQUESTS:
            return

        def loop():
            while self._alive:
                try:
                    self.fetch_data()
                except Exception as exc:
                    print(f"[{self.__class__.__name__}] refresh error: {exc}")
                time.sleep(self.REFRESH_INTERVAL)

        run_in_thread(loop)

    def destroy(self):
        self._alive = False


class DateTimeWidget(BaseWidget):
    REFRESH_INTERVAL = 999999

    def build(self):
        self.header("DATE & TIME")

        time_fs = self.fs(44 if self.big else 34)
        date_fs = self.fs(18 if self.big else 14)

        # Expandable spacers center the content vertically in the card.
        tk.Frame(self.inner, bg=self.colors["widget_bg"]).pack(fill="both", expand=True)

        self.lbl_time = tk.Label(
            self.inner, text="--:--:--",
            font=(FONT_FAMILY, time_fs, "bold"),
            bg=self.colors["widget_bg"], fg=self.colors["text"],
        )
        self.lbl_time.pack(pady=(6, 2))

        self.lbl_date = tk.Label(
            self.inner, text="",
            font=(FONT_FAMILY, date_fs),
            bg=self.colors["widget_bg"], fg=get_contrast_aware_text_color(self.colors["widget_bg"], self.colors["accent"]),
        )
        self.lbl_date.pack()

        if self.big:
            self.lbl_day = tk.Label(
                self.inner, text="",
                font=(FONT_FAMILY, self.fs(15)),
                bg=self.colors["widget_bg"], fg=self.colors["muted"],
            )
            self.lbl_day.pack(pady=(6, 0))

        tk.Frame(self.inner, bg=self.colors["widget_bg"]).pack(fill="both", expand=True)

        self._tick()

    def _tick(self):
        if not self._alive:
            return
        now = datetime.now()
        self.lbl_time.config(text=now.strftime("%H:%M:%S"))
        self.lbl_date.config(text=now.strftime("%d. %B %Y"))
        if self.big and hasattr(self, "lbl_day"):
            self.lbl_day.config(text=now.strftime("%A"))
        self.inner.after(1000, self._tick)


class WeatherWidget(BaseWidget):
    REFRESH_INTERVAL = 600

    def build(self):
        self.header("WEATHER")

        temp_fs = self.fs(44 if self.big else 32)
        desc_fs = self.fs(15 if self.big else 12)
        tk.Frame(self.inner, bg=self.colors["widget_bg"]).pack(fill="both", expand=True)

        self.lbl_temp = tk.Label(
            self.inner, text="--°C",
            font=(FONT_FAMILY, temp_fs, "bold"),
            bg=self.colors["widget_bg"], fg=self.colors["text"],
        )
        self.lbl_temp.pack(pady=(6, 0))

        self.lbl_desc = tk.Label(
            self.inner, text="Loading weather data...",
            font=(FONT_FAMILY, desc_fs),
            bg=self.colors["widget_bg"], fg=get_contrast_aware_text_color(self.colors["widget_bg"], self.colors["accent"]),
        )
        self.lbl_desc.pack(pady=(2, 4))

        if self.big:
            self.lbl_location = tk.Label(
                self.inner, text="",
                font=(FONT_FAMILY, self.fs(13)),
                bg=self.colors["widget_bg"], fg=self.colors["muted"],
            )
            self.lbl_location.pack(pady=(4, 0))

            self.lbl_details = tk.Label(
                self.inner, text="",
                font=(FONT_FAMILY, self.fs(13)),
                bg=self.colors["widget_bg"], fg=self.colors["muted"],
            )
            self.lbl_details.pack(pady=(4, 0))

        tk.Frame(self.inner, bg=self.colors["widget_bg"]).pack(fill="both", expand=True)

    def fetch_data(self):
        if not HAS_REQUESTS:
            self.ui(lambda: self.lbl_desc.config(text="requests not installed"))
            return
        location_name = self.settings.get("location", "")

        try:
            data = _fetch_open_meteo_current(self.settings.get("coordinates") or {})
            self.ui(lambda: self._show_weather(
                data["temp"], data["feels"], data["desc"], data["icon"],
                data["wind"], location_name
            ))
        except requests.exceptions.RequestException:
            self.ui(self._show_weather_offline)
        except Exception:
            self.ui(lambda: self.lbl_desc.config(text="Weather error."))

    def _show_weather_offline(self):
        last = getattr(self, "_last_weather", None)
        if last:
            # Keep showing the last known values (marked stale) instead of a raw
            # error dump; the next automatic refresh retries anyway.
            self._show_weather(
                last["temp"], last["feels"], last["desc"], last["icon"],
                last["wind"], last["location"],
            )
            self.lbl_desc.config(text=f"{last['desc']} (offline)")
        else:
            self.lbl_temp.config(text="--°C")
            self.lbl_desc.config(text="Weather service not reachable.\nRetrying...")

    def _show_weather(self, temp, feels, desc, icon, wind, location_name):
        self._last_weather = {
            "temp": temp, "feels": feels, "desc": desc, "icon": icon,
            "wind": wind, "location": location_name,
        }
        self.lbl_temp.config(text=f"{temp}°C")
        self.lbl_desc.config(text=desc)

        if self.big:
            self.lbl_location.config(text=location_name if location_name else "")
            self.lbl_details.config(
                text=f"Feels like {feels}°C - Wind {wind} km/h"
            )


class CalendarWidget(BaseWidget):
    REFRESH_INTERVAL = 300

    def build(self):
        self.header("CALENDAR")
        self.list_frame = tk.Frame(self.inner, bg=self.colors["widget_bg"])
        self.list_frame.pack(fill="both", expand=True)
        self._set_status("Loading calendar...")

    def fetch_data(self):
        if not HAS_REQUESTS:
            self._set_status("requests not installed")
            return
        try:
            r = requests.get(f"{SERVER_URL}/calendar/events", timeout=6)
            if r.status_code == 401:
                # Google logins live in each browser's localStorage — the
                # desktop app has none, so this widget can't show data here.
                self.ui(lambda: self._set_status(
                    "Google login is per browser.\nUse the web dashboard\n(Start Dashboard)."))
                return
            if r.status_code != 200:
                self.ui(lambda: self._set_status(f"Server error: {r.status_code}"))
                return
            events = r.json().get("events", [])
            self.ui(lambda: self._render_events(events))
        except requests.exceptions.RequestException:
            self.ui(lambda: self._set_status("Server not reachable.\n-> Start server.py"))
        except Exception as exc:
            err = str(exc)[:50]
            self.ui(lambda: self._set_status(f"Error: {err}"))

    def _render_events(self, events):
        self._clear()
        max_ev = 6 if self.big else 3
        if not events:
            self._set_status("No upcoming events")
            return
        for ev in events[:max_ev]:
            start_raw = (ev.get("start") or {}).get("dateTime") or (ev.get("start") or {}).get("date", "")
            try:
                dt = datetime.fromisoformat(start_raw.replace("Z", "+00:00"))
                start_fmt = dt.strftime("%m-%d %H:%M")
            except Exception:
                start_fmt = start_raw[:10]
            summary = (ev.get("summary") or "No title")[:35]

            row = tk.Frame(self.list_frame, bg=self.colors["widget_bg"])
            row.pack(fill="x", pady=3)
            tk.Label(row, text=start_fmt, font=(FONT_FAMILY, self.fs(12)),
                    bg=self.colors["widget_bg"], fg=get_contrast_aware_text_color(self.colors["widget_bg"], self.colors["accent"]),
                    width=14, anchor="w").pack(side="left")
            tk.Label(row, text=summary, font=(FONT_FAMILY, self.fs(12)),
                    bg=self.colors["widget_bg"], fg=self.colors["text"],
                    anchor="w").pack(side="left")

    def _clear(self):
        for w in self.list_frame.winfo_children():
            w.destroy()

    def _set_status(self, msg: str):
        self._clear()
        tk.Label(self.list_frame, text=msg, font=(FONT_FAMILY, self.fs(13)),
                bg=self.colors["widget_bg"], fg=self.colors["muted"],
                justify="left", anchor="w").pack(fill="x")


class StockCryptoWidget(BaseWidget):
    REFRESH_INTERVAL = 120

    def build(self):
        self._sels = _stock_crypto_selections(self.settings)

        self.header("STOCKS")

        self._rows_frame = tk.Frame(self.inner, bg=self.colors["widget_bg"])
        self._rows_frame.pack(fill="x")

        self._rows = []
        accent_text = get_contrast_aware_text_color(
            self.colors["widget_bg"], self.colors["accent"]
        )
        fs_sym = self.fs(12 if self.big else 10)
        for idx, sel in enumerate(self._sels):
            row = tk.Frame(self._rows_frame, bg=self.colors["widget_bg"])
            row.pack(fill="x", pady=1)

            lbl_sym = tk.Label(row, text=sel["symbol"],
                               font=(FONT_FAMILY, fs_sym, "bold"),
                               bg=self.colors["widget_bg"], fg=accent_text)
            lbl_sym.pack(side="left")
            if self.big:
                lbl_name = tk.Label(row, text=sel["name"],
                                    font=(FONT_FAMILY, max(fs_sym - 2, 7)),
                                    bg=self.colors["widget_bg"], fg=self.colors["muted"])
                lbl_name.pack(side="left", padx=(6, 0))

            lbl_price = tk.Label(row, text="--",
                                 font=(FONT_FAMILY, fs_sym),
                                 bg=self.colors["widget_bg"], fg=self.colors["text"])
            lbl_price.pack(side="right")

            # Per-row status slot: normally empty; carries only a short error
            # hint when that row's price cannot be fetched. No +/- change and
            # no chart — a dashboard is a passive price display.
            lbl_status = tk.Label(row, text="",
                                  font=(FONT_FAMILY, max(fs_sym - 1, 7)),
                                  bg=self.colors["widget_bg"], fg=self.colors["muted"])
            lbl_status.pack(side="right", padx=(0, 6))

            self._rows.append({
                "sel": sel, "frame": row,
                "price": lbl_price, "status": lbl_status,
            })

    def fetch_data(self):
        """Prices for every selected symbol (worker thread context)."""
        if not HAS_REQUESTS:
            return
        for idx, entry in enumerate(self._rows):
            if not self._alive:
                return
            sel = entry["sel"]
            row_token = (idx, f"{sel['symbol']}/{sel['type']}")

            def deliver(data, i=idx, rt=row_token):
                """Worker-thread callback: compute the row's new texts here and
                hand every Tk update to the queue (Tk is not thread-safe)."""
                if not self._alive:
                    return
                row = self._rows[i] if i < len(self._rows) else None
                if not row:
                    return
                cur = row["sel"]
                if f"{cur['symbol']}/{cur['type']}" != rt[1]:
                    return  # selection changed since the request started
                if data.get("price") is None:
                    fill_text = data.get("price_text", "Error")
                    err_text = (data.get("error") or "No data")[:40]

                    def show_error(row=row, fill=fill_text, err=err_text):
                        # keep the old value; only refresh a still-empty row
                        if row["price"].cget("text") == "--":
                            row["price"].config(text=fill)
                        row["status"].config(text=err, fg=self.colors["muted"])

                    self.ui(show_error)
                    return
                price = float(data["price"])
                price_text = f"${price:,.2f}"

                def show_price(row=row, txt=price_text):
                    row["price"].config(text=txt)
                    row["status"].config(text="")

                self.ui(show_price)

            try:
                r = requests.get(
                    f"{SERVER_URL}/finance/price",
                    params={"type": sel["type"], "symbol": sel["symbol"],
                            "name": sel["name"]},
                    timeout=10,
                )
                if r.status_code == 200:
                    deliver(r.json())
                else:
                    try:
                        err = r.json().get("error", f"HTTP {r.status_code}")
                    except Exception:
                        err = f"HTTP {r.status_code}"
                    deliver({"price": None, "error": str(err)[:40]})
            except requests.exceptions.RequestException as exc:
                err = "Server off" if "ConnectionError" in type(exc).__name__ else str(exc)[:40]
                deliver({"price": None, "error": err})
            except Exception as exc:
                deliver({"price": None, "error": str(exc)[:40]})


class NotificationsWidget(BaseWidget):
    REFRESH_INTERVAL = 180

    def build(self):
        self.header("MESSAGES")
        self.list_frame = tk.Frame(self.inner, bg=self.colors["widget_bg"])
        self.list_frame.pack(fill="both", expand=True)
        self._set_status("Loading messages...")

    def fetch_data(self):
        if not HAS_REQUESTS:
            self._set_status("requests not installed")
            return
        try:
            r = requests.get(f"{SERVER_URL}/notifications/messages", timeout=8)
            if r.status_code == 401:
                self.ui(lambda: self._set_status(
                    "Google login is per browser.\nUse the web dashboard\n(Start Dashboard)."))
                return
            if r.status_code == 403:
                self.ui(lambda: self._set_status(
                    "Google login is per browser.\nUse the web dashboard\n(Start Dashboard)."))
                return
            if r.status_code != 200:
                try:
                    server_err = (r.json().get("error") or "").strip()
                except Exception:
                    server_err = ""
                err = server_err or f"Server error: {r.status_code}"
                self.ui(lambda: self._set_status(err))
                return
            messages = r.json().get("messages", [])
            self.ui(lambda: self._render_messages(messages))
        except requests.exceptions.RequestException:
            self.ui(lambda: self._set_status("Server not reachable.\n-> Start server.py"))
        except Exception as exc:
            err = str(exc)[:50]
            self.ui(lambda: self._set_status(f"Error: {err}"))

    def _row_linespace(self, size):
        return tkfont.Font(family=FONT_FAMILY, size=size).metrics("linespace")

    def _max_messages(self):
        """Fallback row budget when the window isn't laid out yet.

        Normally _trim_overflow clamps the list to the card's real height, so
        this is only used before the first layout pass. The old fixed cap
        (3 normal / 6 big) left big cards half empty; the server only sends
        10 messages, so there's never a point rendering more.
        """
        if not self.card_h_px:
            return 6 if self.big else 3
        row_h = 2 * self._row_linespace(self.fs(11)) + 10
        available = self.card_h_px - 24 - (self._row_linespace(self.fs(12)) + 20)
        return max(1, min(int(available / row_h), 10))

    def _render_messages(self, messages):
        self._clear()
        if not messages:
            self._set_status("No new messages")
            return
        # Render everything the server sent, then clamp to what really fits.
        for msg in messages[:10]:
            self._append_row(msg)
        self.list_frame.update_idletasks()
        self._trim_overflow()
        # Re-layout after rows were dropped, so the fit below measures the
        # labels at their final sizes.
        self.list_frame.update_idletasks()
        self._fit_labels()

    def _append_row(self, msg):
        is_unread = msg.get("unread", False)
        row = tk.Frame(self.list_frame, bg=self.colors["widget_bg"])
        row.pack(fill="x", pady=2)

        dot_color = self.colors["accent"] if is_unread else self.colors["muted"]
        tk.Label(row, text="*" if is_unread else "-",
                font=(FONT_FAMILY, self.fs(12)), bg=self.colors["widget_bg"],
                fg=dot_color, width=2).pack(side="left")

        info = tk.Frame(row, bg=self.colors["widget_bg"])
        info.pack(side="left", fill="x", expand=True)

        row.lbl_from = tk.Label(info, text=_mask_email_sender(msg.get("from")),
                font=(FONT_FAMILY, self.fs(11), "bold"),
                bg=self.colors["widget_bg"],
                fg=self.colors["text"] if is_unread else self.colors["muted"],
                anchor="w")
        row.lbl_from.pack(fill="x")
        row.lbl_subj = tk.Label(info, text=msg.get("subject") or "(no subject)",
                font=(FONT_FAMILY, self.fs(11)),
                bg=self.colors["widget_bg"], fg=self.colors["muted"],
                anchor="w")
        row.lbl_subj.pack(fill="x")
        return row

    def _trim_overflow(self):
        """Drop rows that would extend past the card's visible height."""
        avail = self.list_frame.winfo_height()
        if avail <= 1:
            # Not laid out yet — fall back to the height estimate.
            while len(self.list_frame.winfo_children()) > self._max_messages():
                self.list_frame.winfo_children()[-1].destroy()
            return
        rows = self.list_frame.winfo_children()
        total = sum(r.winfo_reqheight() for r in rows)
        while rows and total > avail:
            rows[-1].destroy()
            rows = self.list_frame.winfo_children()
            total = sum(r.winfo_reqheight() for r in rows)

    def _fit_labels(self):
        """Truncate sender/subject to the card width (ellipsis if needed).

        Senders already arrive masked (name only, or j***@domain — see
        _mask_email_sender); the "<address>" tail shortcut only ever hits on
        masked fallbacks, truncation stays purely cosmetic.
        """
        for row in self.list_frame.winfo_children():
            self._fit_one(row.lbl_from, keep_tail=True)
            self._fit_one(row.lbl_subj)

    def _fit_one(self, label, keep_tail=False):
        text = label.cget("text")
        width = label.winfo_width()
        if not text or width <= 1:
            return
        font = tkfont.Font(font=label.cget("font"))
        if font.measure(text) <= width:
            return
        if keep_tail:
            lt = text.rfind("<")
            gt = text.rfind(">")
            if 0 < lt < gt:
                addr = text[lt:gt + 1]
                if font.measure(addr) <= width:
                    label.config(text=addr)
                    return
        # Longest prefix that fits together with an ellipsis.
        ell = "..."
        lo, hi = 0, len(text)
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if font.measure(text[:mid] + ell) <= width:
                lo = mid
            else:
                hi = mid - 1
        label.config(text=text[:lo] + ell)

    def _clear(self):
        for w in self.list_frame.winfo_children():
            w.destroy()

    def _set_status(self, msg: str):
        self._clear()
        tk.Label(self.list_frame, text=msg, font=(FONT_FAMILY, self.fs(13)),
                bg=self.colors["widget_bg"], fg=self.colors["muted"],
                justify="left", anchor="w").pack(fill="x")


class CountdownWidget(BaseWidget):
    REFRESH_INTERVAL = 999999

    def build(self):
        self.header("COUNTDOWN")

        cd = self.settings.get("countdown") or {}
        self._label_text = cd.get("label") or cd.get("name") or "Event"
        self._target_date = cd.get("date") or cd.get("targetDate") or ""

        if not self._target_date:
            self._target_date = (
                self.settings.get("countdownDate")
                or self.settings.get("countdown_date")
                or ""
            )
        if self._label_text == "Event":
            self._label_text = (
                self.settings.get("countdownLabel")
                or self.settings.get("countdown_label")
                or "Event"
            )

        tk.Frame(self.inner, bg=self.colors["widget_bg"]).pack(fill="both", expand=True)

        self.lbl_event = tk.Label(
            self.inner, text=self._label_text,
            font=(FONT_FAMILY, self.fs(16 if self.big else 13)),
            bg=self.colors["widget_bg"], fg=get_contrast_aware_text_color(self.colors["widget_bg"], self.colors["accent"]),
        )
        self.lbl_event.pack(pady=(4, 0))

        cd_fs = self.fs(30 if self.big else 22)
        self.lbl_cd = tk.Label(
            self.inner, text="-- days",
            font=(FONT_FAMILY, cd_fs, "bold"),
            bg=self.colors["widget_bg"], fg=self.colors["text"],
        )
        self.lbl_cd.pack(pady=10)

        self.lbl_date = tk.Label(
            self.inner, text="",
            font=(FONT_FAMILY, self.fs(12)),
            bg=self.colors["widget_bg"], fg=self.colors["muted"],
        )
        self.lbl_date.pack()

        tk.Frame(self.inner, bg=self.colors["widget_bg"]).pack(fill="both", expand=True)

        if not self._target_date:
            self.lbl_cd.config(text="No date set")
            self.lbl_date.config(text="Set date in Settings")
        else:
            self._tick()

    def _tick(self):
        if not self._alive:
            return
        try:
            target = datetime.fromisoformat(self._target_date)
            if target.tzinfo is not None:
                # tz-aware date (ISO string with Z or offset) -> normalize to
                # local naive time so the subtraction below cannot raise a
                # TypeError (naive vs aware datetime).
                target = target.astimezone().replace(tzinfo=None)
        except ValueError:
            self.lbl_cd.config(text="Invalid date")
            return

        now = datetime.now()
        diff = target - now

        if diff.total_seconds() <= 0:
            self.lbl_cd.config(text="Reached!")
            self.lbl_date.config(text=target.strftime("%m-%d %Y"))
            return

        total_secs = int(diff.total_seconds())
        days = total_secs // 86400
        hours = (total_secs % 86400) // 3600
        mins = (total_secs % 3600) // 60
        secs = total_secs % 60

        if days > 0:
            self.lbl_cd.config(text=f"{days}D {hours:02d}:{mins:02d}:{secs:02d}")
        else:
            self.lbl_cd.config(text=f"{hours:02d}:{mins:02d}:{secs:02d}")

        self.lbl_date.config(text=f"Target: {target.strftime('%m-%d %Y %H:%M')}")
        self.inner.after(1000, self._tick)


WIDGET_CLASSES = {
    "dateTime": DateTimeWidget,
    "weather": WeatherWidget,
    "calendar": CalendarWidget,
    "stockCrypto": StockCryptoWidget,
    "notifications": NotificationsWidget,
    "countdown": CountdownWidget,
}


def make_widget(parent, key, colors, big, settings, scale=1.0, card_h_px=None):
    cls = WIDGET_CLASSES.get(key)
    if cls:
        return cls(parent, colors, big=big, settings=settings, scale=scale, card_h_px=card_h_px)
    return None  # unknown keys simply don't render; the caller skips them


# --- Widget layout (free-form, Windows-11-style) --------------------------
#
# Settings carry a "widgetLayout" object:
#   { "preset": "twoUnequal" | "quadrants" | "threeColumns" | "threeUnequal",
#     "cells": { "weather": {"x": 0, "y": 0, "w": 45, "h": 100}, ... } }
# Each enabled widget has a rectangle in percent of the dashboard area and
# can be moved/resized freely (no snapping). Only enabled widgets are
# placed, so there are never empty cards.

LAYOUT_PRESETS = {"twoUnequal", "quadrants", "threeColumns", "threeUnequal"}


def auto_layout(preset, keys):
    """Default rectangles (x, y, w, h in percent) for the given widgets."""
    keys = list(keys)
    n = len(keys)
    cells = {}

    if preset == "twoUnequal":
        # First widget: tall left column. Rest: stacked on the right.
        if n:
            cells[keys[0]] = {"x": 0.0, "y": 0.0, "w": 45.0, "h": 100.0}
        nrows = max(1, n - 1)
        for i, key in enumerate(keys[1:]):
            cells[key] = {"x": 46.0, "y": 100.0 * i / nrows, "w": 54.0, "h": 100.0 / nrows}
    elif preset in ("threeColumns", "threeUnequal"):
        cols = [33.0, 33.0, 34.0] if preset == "threeColumns" else [25.0, 45.0, 30.0]
        nrows = max(1, math.ceil(n / 3))
        for i, key in enumerate(keys):
            cx = sum(cols[: i % 3])
            cells[key] = {"x": cx, "y": 100.0 * (i // 3) / nrows, "w": cols[i % 3], "h": 100.0 / nrows}
    else:  # quadrants: 2x2, grows by adding rows of two
        nrows = max(2, math.ceil(n / 2))
        for i, key in enumerate(keys):
            cells[key] = {"x": (i % 2) * 50.0, "y": 100.0 * (i // 2) / nrows, "w": 50.0, "h": 100.0 / nrows}
    return cells


# Approximate content height (px) of each widget at scale 1.0. Used to cap
# font scaling by the card's real height, so text never gets taller than the
# card that contains it (area-based scaling alone inflates fonts on
# wide-but-short cards and clips them).
NATURAL_HEIGHT = {
    "weather": 125,
    "dateTime": 120,
    "stockCrypto": 135,
    "notifications": 135,
    "calendar": 150,
    "countdown": 125,
}
BIG_EXTRA_HEIGHT = 75  # featured cards (taller than half the screen) show extra rows


def resolve_widget_layout(enabled_keys, layout):
    """Return validated free-form rectangles for the enabled widgets.

    Uses the saved layout when consistent (also converting legacy grid-format
    cells); otherwise falls back to the preset's auto layout.
    """
    layout = layout or {}
    preset = layout.get("preset") or "twoUnequal"
    if preset not in LAYOUT_PRESETS:
        preset = "twoUnequal"
    cells = layout.get("cells") or {}

    columns = [float(v) for v in (layout.get("columns") or []) if isinstance(v, (int, float)) and v > 0]
    rows = [float(v) for v in (layout.get("rows") or []) if isinstance(v, (int, float)) and v > 0]

    rects = {}
    valid = True
    for key in enabled_keys:
        cell = cells.get(key)
        if not cell:
            continue
        if all(k in cell for k in ("x", "y", "w", "h")):
            x, y, w, h = (float(cell[k]) for k in ("x", "y", "w", "h"))
        elif all(k in cell for k in ("c", "r", "cs", "rs")) and columns and rows:
            # Legacy grid format -> rectangles
            ncols, nrows = len(columns), len(rows)
            col_total = sum(columns)
            row_total = sum(rows)
            c, r = int(cell["c"]), int(cell["r"])
            cs = max(1, int(cell.get("cs", 1)))
            rs = max(1, int(cell.get("rs", 1)))
            if c < 0 or r < 0 or c + cs > ncols or r + rs > nrows:
                valid = False
                break
            x = sum(columns[:c]) / col_total * 100.0
            w = sum(columns[c:c + cs]) / col_total * 100.0
            y = sum(rows[:r]) / row_total * 100.0
            h = sum(rows[r:r + rs]) / row_total * 100.0
        else:
            valid = False
            break
        if w <= 0 or h <= 0 or x < -0.01 or y < -0.01 or x + w > 100.01 or y + h > 100.01:
            valid = False
            break
        rects[key] = {"x": x, "y": y, "w": w, "h": h}

    if not valid or any(k not in rects for k in enabled_keys):
        return auto_layout(preset, enabled_keys)
    return rects


class Dashboard(tk.Tk):
    def __init__(self):
        register_orbitron_private()  # bundled Orbitron for Tk, before first use
        super().__init__()
        self.settings = load_settings()
        self.colors = extract_colors(self.settings)
        self._widgets = []
        self._settings_mtime = settings_file_mtime()

        self._setup_window()
        self._build_ui()
        self._watch_settings()

    def _watch_settings(self):
        """Hot-reload: when settings.json changes (e.g. "Save Settings" on the
        website), rebuild the dashboard with the new settings within ~1 second."""
        mtime = settings_file_mtime()
        if mtime is not None and mtime != self._settings_mtime:
            self._settings_mtime = mtime
            new_settings = load_settings()
            if new_settings and new_settings != self.settings:
                self.settings = new_settings
                self.colors = extract_colors(new_settings)
                self.configure(bg=self.colors["bg"])
                self._build_ui()
        self.after(1000, self._watch_settings)

    def _setup_window(self):
        self.title("Dashboard")
        self.configure(bg=self.colors["bg"])
        self.attributes("-fullscreen", True)

        # Taskbar / title-bar icon (keeps a reference so the image isn't GC'd).
        self._icon_ref = None
        icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "favicon.png")
        if os.path.exists(icon_path):
            try:
                self._icon_ref = tk.PhotoImage(file=icon_path)
                self.iconphoto(True, self._icon_ref)
            except tk.TclError:
                self._icon_ref = None

        self.bind("<Escape>", lambda e: self.attributes("-fullscreen", False))
        self.bind("<F11>", lambda e: self.attributes("-fullscreen", True))
        self.bind("<q>", lambda e: self.destroy())
        self.bind("<Q>", lambda e: self.destroy())
        self.bind("<r>", lambda e: self._soft_reload())
        self.bind("<R>", lambda e: self._soft_reload())

    def _soft_reload(self):
        self.destroy()
        python = sys.executable
        os.execl(python, python, *sys.argv)

    def _build_ui(self):
        c = self.colors
        widgets_en = self.settings.get("widgets") or {}

        # Only enabled widgets are rendered — disabled ones leave no empty card.
        enabled = [k for k, v in widgets_en.items() if v]
        if not enabled:
            enabled = ["dateTime"]

        # Respect the widget order chosen in Settings -> Align Widgets
        # (unknown/disabled entries are ignored, new widgets get appended).
        order = self.settings.get("widgetOrder") or []
        ordered = [k for k in order if k in enabled] + [k for k in enabled if k not in order]
        enabled = ordered

        # Stop old widgets (kills their refresh threads and pending ticks)
        # and clear the previous build when hot-reloading.
        for widget in self._widgets:
            widget.destroy()
        self._widgets = []

        if not hasattr(self, "root_frame"):
            self.root_frame = tk.Frame(self, bg=c["bg"])
            self.root_frame.pack(fill="both", expand=True, padx=22, pady=18)
        else:
            self.root_frame.configure(bg=c["bg"])
            for child in self.root_frame.winfo_children():
                child.destroy()

        self._build_header(self.root_frame)

        content = tk.Frame(self.root_frame, bg=c["bg"])
        content.pack(fill="both", expand=True, pady=(14, 0))

        # Free-form layout: each widget is a rectangle in percent of the
        # content area, placed with `place` (no grid snapping). A small inset
        # leaves a gap between the cards.
        rects = resolve_widget_layout(enabled, self.settings.get("widgetLayout"))
        margin = 0.006

        # Estimate the content area height in pixels so font scaling can be
        # capped by each card's real height (see NATURAL_HEIGHT above).
        content_h_px = max(200, self.winfo_screenheight() - 145)

        for key in enabled:
            rect = rects.get(key)
            if rect is None:
                continue

            # Tall cards (more than half the height) are the "featured" ones.
            big = rect["h"] > 50

            # Scale fonts to the card's footprint so the content fills the
            # card instead of leaving most of it empty — but never taller than
            # the card itself.
            area_frac = (rect["w"] / 100.0) * (rect["h"] / 100.0)
            scale = (area_frac / 0.10) ** 0.5
            card_h_px = content_h_px * rect["h"] / 100.0
            # 10% headroom on the estimate so padding never clips the last row.
            natural = (NATURAL_HEIGHT.get(key, 150) + (BIG_EXTRA_HEIGHT if big else 0)) * 1.10
            scale = max(0.8, min(scale, card_h_px / natural, 2.6))
            widget = make_widget(content, key, c, big=big, settings=self.settings, scale=scale, card_h_px=card_h_px)
            if widget is None:
                continue

            widget.container_frame.place(
                relx=rect["x"] / 100.0 + margin,
                rely=rect["y"] / 100.0 + margin,
                relwidth=rect["w"] / 100.0 - 2 * margin,
                relheight=rect["h"] / 100.0 - 2 * margin,
            )
            self._widgets.append(widget)

        self._build_footer(self.root_frame)

    def _build_header(self, parent):
        c = self.colors
        hdr = tk.Frame(parent, bg=c["bg"])
        hdr.pack(fill="x", pady=(2, 6))

        # Kontrastbewusste Textfarbe für Dashboard-Titel
        bg_color = c["bg"]
        accent_color = c["accent"]
        header_text_color = get_contrast_aware_text_color(bg_color, accent_color)

        tk.Label(
            hdr,
            text="DASHBOARD",
            font=(FONT_FAMILY, 20, "bold"),
            bg=c["bg"], fg=header_text_color,
        ).pack()

        # Accent rule under the header
        tk.Frame(parent, height=2, bg=accent_color).pack(fill="x", pady=(2, 0))

    def _build_footer(self, parent):
        c = self.colors
        location = self.settings.get("location", "")
        if not location:
            return
        tk.Frame(parent, height=1, bg=self.colors["border"]).pack(fill="x", pady=(8, 5))
        footer = tk.Frame(parent, bg=c["bg"])
        footer.pack(fill="x")

        # Keep showing the location; no decoration point in front of it.
        tk.Label(
            footer,
            text=location,
            font=(FONT_FAMILY, 9),
            bg=c["bg"], fg=c["muted"],
        ).pack(side="right")


# ===== Streamlit / Web rendering (mirrors the Tkinter dashboard) =====
# The same widget logic (data fetching, layout, theme) is reused, but instead
# of building Tk widgets we emit HTML that Streamlit renders in the browser.

def _ttl_cache(seconds: float):
    """Memoize a renderer fetch across Streamlit reruns.

    Module-level state does not survive a Streamlit rerun, so a plain
    dictionary cache would reset and every run would re-hit the HTTP
    endpoints; ``st.cache_data`` persists across runs per process. Reruns now
    only happen when the page is (re)loaded — live widget data refreshes
    client-side — but the initial load still runs several sequential fetches.
    Outside a Streamlit context (e.g. plain-script tests) it is a passthrough.
    """
    try:
        import streamlit as st
    except ImportError:
        st = None
    if st is not None:
        return st.cache_data(ttl=seconds, max_entries=8, show_spinner=False)

    def passthrough(fn):
        return fn

    return passthrough


@_ttl_cache(15.0)
def _fetch_weather_data_for_render(settings):
    """Standalone weather fetch used by the HTML renderer (mirrors WeatherWidget.fetch_data).

    Raises the underlying requests exception on failure instead of returning an
    error dict: ``st.cache_data`` does not cache raised exceptions, so a
    transient outage never sticks in the 15s cache. ``render_weather_html``
    turns the exception into a friendly message; the widget's client-side
    poller (and the next page load) keeps retrying.
    """
    if not HAS_REQUESTS:
        raise RuntimeError("requests not installed")
    data = _fetch_open_meteo_current(settings.get("coordinates") or {}, attempts=2, timeout=4)
    data["location"] = settings.get("location", "")
    return data


def _esc(text):
    """HTML-escape a user-provided string for safe embedding in the markup."""
    import html as _html_mod
    return _html_mod.escape(str(text), quote=True)


def _stock_crypto_selections(settings):
    """The stocks widget's selection list (max 6, back-compat, BTC default).

    New settings store ``stockCryptoSelections``: a list of
    ``{type, symbol, name, id}``. Older settings still hold a single
    ``stockCryptoSelection`` dict — that is wrapped into a one-element list.
    """
    raw = settings.get("stockCryptoSelections")
    out = []
    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, dict) and item.get("symbol"):
                out.append({
                    "type": item.get("type") or "crypto",
                    "symbol": str(item.get("symbol")),
                    "name": str(item.get("name") or item.get("symbol")),
                    "id": item.get("id"),
                })
    if not out:
        single = settings.get("stockCryptoSelection")
        if isinstance(single, dict) and single.get("symbol"):
            out.append({
                "type": single.get("type") or "crypto",
                "symbol": str(single.get("symbol")),
                "name": str(single.get("name") or single.get("symbol")),
                "id": single.get("id"),
            })
    if not out:
        out = [{"type": "crypto", "symbol": "BTC", "name": "Bitcoin", "id": "bitcoin"}]
    return out[:6]


@_ttl_cache(15.0)
def _fetch_one_price_for_render(symbol, name, stype):
    if not HAS_REQUESTS:
        return {"error": "requests not installed"}
    try:
        r = requests.get(
            f"{SERVER_URL}/finance/price",
            params={"type": stype, "symbol": symbol, "name": name},
            timeout=10,
        )
        if r.status_code == 200:
            data = r.json()
            return {"price": data.get("price"), "change": data.get("change") or 0,
                    "marketCap": data.get("marketCap"), "symbol": symbol, "name": name, "type": stype}
        try:
            err = r.json().get("error", f"HTTP {r.status_code}")
        except Exception:
            err = f"HTTP {r.status_code}"
        return {"error": err[:40]}
    except requests.exceptions.RequestException:
        return {"error": "-> Start server.py", "price_text": "Server off"}


def _inject_css(colors):
    bg = colors["bg"]
    widget_bg = colors["widget_bg"]
    accent = colors["accent"]
    text = colors["text"]
    border = colors["border"]
    muted = colors["muted"]
    positive = colors["positive"]
    negative = colors["negative"]
    header_text = get_contrast_aware_text_color(bg, accent)
    css = f"""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Orbitron:wght@400..900&display=swap');
    html, body, .main {{ margin: 0; padding: 0; font-family: 'Orbitron', sans-serif; background: {bg}; height: 100%; }}
    #dashboard-header {{ padding: 2px 0 6px; text-align: center; }}
    #dashboard-header h1 {{ margin: 0; font-size: 20px; font-weight: 700; letter-spacing: 2px; color: {header_text}; }}
    #dashboard-header .accent-line {{ height: 2px; width: 72px; background: {accent}; margin: 4px auto 0; }}
    #dashboard-content {{ position: relative; width: 100%; height: calc(100vh - 118px); margin-top: 14px; overflow: hidden; }}
    #dashboard-footer {{
        display: flex; justify-content: flex-end; align-items: center;
        padding: 8px 0 5px; border-top: 1px solid rgba(255,255,255,0.08);
        margin-top: 8px; font-size: 9px; color: {muted};
    }}
    .widget-card {{
        position: absolute; border-radius: 30px; border: 1px solid {border};
        padding: 18px; box-sizing: border-box; overflow: hidden;
        display: flex; flex-direction: column; background: {widget_bg};
    }}
    .widget-header {{ display: flex; align-items: center; gap: 6px; margin-bottom: 8px; }}
    .widget-header-title {{ font-size: 12px; font-weight: 700; letter-spacing: 1px; color: {header_text}; }}
    .widget-header-line {{ height: 2px; width: 72px; background: {accent}; margin-bottom: 10px; }}
    .widget-spacer {{ flex: 1; }}
    .widget-text-center {{ text-align: center; }}
    .widget-time, .widget-temp, .widget-price, .widget-countdown {{ text-align: center; font-weight: 700; }}
    .widget-text, .widget-time, .widget-temp, .widget-price, .widget-countdown {{ color: {text}; }}
    .widget-accent-text {{ color: {header_text}; }}
    .widget-muted-text {{ color: {muted}; }}
    .widget-positive {{ color: {positive}; }}
    .widget-negative {{ color: {negative}; }}
    .widget-list {{ flex: 1; display: flex; flex-direction: column; gap: 2px; overflow: hidden; }}
    .widget-list-row {{ display: flex; align-items: center; gap: 8px; padding: 3px 0; }}
    .widget-list-time {{ font-size: 12px; width: 14ch; flex-shrink: 0; text-align: left; }}
    .widget-list-text {{ font-size: 12px; color: {text}; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
    .widget-msg-row {{ display: flex; align-items: flex-start; gap: 8px; padding: 2px 0; }}
    .widget-msg-dot {{ font-size: 12px; width: 2ch; flex-shrink: 0; text-align: center; }}
    .widget-msg-info {{ flex: 1; min-width: 0; }}
    .widget-msg-from {{ font-size: 11px; font-weight: 700; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
    .widget-msg-subject {{ font-size: 11px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
    .widget-status {{ font-size: 13px; text-align: left; white-space: pre-line; }}
    """ + _STOCKS_CSS \
        .replace("@@HEADER@@", header_text) \
        .replace("@@MUTED@@", muted) \
        .replace("@@TEXT@@", text) \
        .replace("@@BORDER@@", border) + """
    </style>
    """
    return css


# Live clock: the server-rendered date/time widget updates itself client-side,
# so Streamlit never needs to rerun for the time to keep ticking.
_DATETIME_TICKER_JS = """
<script>
(function() {
  var MONTHS = ["January","February","March","April","May","June","July",
                "August","September","October","November","December"];
  var DAYS = ["Sunday","Monday","Tuesday","Wednesday","Thursday","Friday","Saturday"];
  function pad(n) { return (n < 10 ? "0" : "") + n; }
  function tick() {
    var d = new Date();
    var t = document.getElementById("dt-time");
    if (t) t.textContent = pad(d.getHours()) + ":" + pad(d.getMinutes()) + ":" + pad(d.getSeconds());
    var dateEl = document.getElementById("dt-date");
    if (dateEl) dateEl.textContent = pad(d.getDate()) + ". " + MONTHS[d.getMonth()] + " " + d.getFullYear();
    var dayEl = document.getElementById("dt-day");
    if (dayEl) dayEl.textContent = DAYS[d.getDay()];
  }
  tick();
  setInterval(tick, 1000);
})();
</script>
"""


def render_date_time_html(colors, settings, big, scale, content_h_px):
    now = datetime.now()
    time_str = now.strftime("%H:%M:%S")
    date_str = now.strftime("%d. %B %Y")
    header_text = get_contrast_aware_text_color(colors["widget_bg"], colors["accent"])
    time_fs = max(int((44 if big else 34) * scale), 22)
    date_fs = max(int((18 if big else 14) * scale), 10)
    html = f"""
    <div class="widget-header">
        <span class="widget-header-title" style="color:{header_text}">DATE &amp; TIME</span>
    </div>
    <div class="widget-header-line" style="background:{colors['accent']}"></div>
    <div class="widget-spacer"></div>
    <div id="dt-time" class="widget-time" style="font-size:{time_fs}px;color:{colors['text']}">{time_str}</div>
    <div id="dt-date" class="widget-text-center" style="font-size:{date_fs}px;color:{header_text}">{date_str}</div>
    """
    if big:
        day_str = now.strftime("%A")
        day_fs = max(int(15 * scale), 10)
        html += f'<div id="dt-day" class="widget-muted-text" style="font-size:{day_fs}px">{day_str}</div>'
    html += '<div class="widget-spacer"></div>'
    html += _DATETIME_TICKER_JS
    return html


# Weather poller: the browser refreshes this widget directly from open-meteo
# (CORS is allowed there) — no server round-trip, no Streamlit rerun. The old
# values stay on screen whenever a poll fails or is still in flight.
_WEATHER_POLLER_JS = """
<script>
(function() {
  var URL = "@@URL@@";
  var CODES = @@CODES@@;
  var LOC = @@LOC@@;
  var INTERVAL = @@INTERVAL@@;   // 10 min; retried after 30s on failure
  var timer = null;

  function schedule(ms) { clearTimeout(timer); timer = setTimeout(poll, ms); }
  function setText(id, text) {
    var el = document.getElementById(id);
    if (el) el.textContent = text;
  }
  // Only ever called with fresh data — old content is never cleared first.
  function update(cur) {
    var code = CODES[String(cur.weathercode)] || ["Unknown", "?"];
    setText("weather-temp", cur.temperature_2m + "°C");
    setText("weather-desc", code[0]);
    var loc = document.getElementById("weather-loc");
    if (loc && LOC) loc.textContent = LOC;
    setText("weather-details",
      "Feels like " + cur.apparent_temperature + "°C - Wind " +
      cur.windspeed_10m + " km/h");
  }
  function poll() {
    fetch(URL)
      .then(function(r) { return r.ok ? r.json() : null; })
      .then(function(data) {
        schedule(data ? INTERVAL : 30000);
        if (data && data.current) update(data.current);
      })
      .catch(function() { schedule(30000); });
  }
  poll();
})();
</script>
"""


def render_weather_html(colors, settings, big, scale):
    header_text = get_contrast_aware_text_color(colors["widget_bg"], colors["accent"])
    desc_fs = max(int((15 if big else 12) * scale), 10)
    try:
        result = _fetch_weather_data_for_render(settings)
    except Exception:
        # Never show raw exception text (e.g. "HTTPSConnectionPool(host=...");
        # the failure is not cached — the widget's client-side poller and the
        # next page load retry.
        result = None
    html = f"""
    <div class="widget-header">
        <span class="widget-header-title" style="color:{header_text}">WEATHER</span>
    </div>
    <div class="widget-header-line" style="background:{colors['accent']}"></div>
    <div class="widget-spacer"></div>
    """
    if result is None:
        temp_text = "--°C"
        desc_text = "Weather service not reachable."
        loc_text = ""
        details_text = ""
    elif "error" in result:
        # Defensive: fetchers no longer return error dicts, but keep a safe fallback.
        temp_text = "--°C"
        desc_text = "Weather service not reachable."
        loc_text = ""
        details_text = ""
    else:
        temp_text = f"{result['temp']}°C"
        desc_text = result['desc']
        if big:
            loc_text = result['location'] or ""
            details_text = f"Feels like {result['feels']}°C - Wind {result['wind']} km/h"
        else:
            loc_text = ""
            details_text = ""
    temp_fs = max(int((44 if big else 32) * scale), 20)
    html += f'<div id="weather-temp" class="widget-temp" style="font-size:{temp_fs}px;color:{colors["text"]}">{temp_text}</div>'
    html += f'<div id="weather-desc" class="widget-text-center" style="font-size:{desc_fs}px;color:{header_text}">{desc_text}</div>'
    if big:
        details_fs = max(int(13 * scale), 10)
        html += f'<div id="weather-loc" class="widget-muted-text" style="font-size:{details_fs}px">{loc_text}</div>'
        html += f'<div id="weather-details" class="widget-muted-text" style="font-size:{details_fs}px">{details_text}</div>'
    html += '<div class="widget-spacer"></div>'
    # Client-side poller: refreshes this widget only, every 10 min.
    html += (
        _WEATHER_POLLER_JS
        .replace("@@URL@@", _open_meteo_url(settings.get("coordinates") or {}))
        .replace("@@CODES@@", json.dumps(WEATHER_CODES))
        .replace("@@LOC@@", json.dumps(settings.get("location", "")))
        .replace("@@INTERVAL@@", "600000")
    )
    return html


# Google data widgets (calendar / messages) render CLIENT-SIDE: the browser
# owning the Google login (localStorage) fetches the data itself with its own
# token, and the server merely proxies the API call. This keeps each browser
# strictly isolated to its own account and keeps every token out of the
# server. The iframe (srcdoc) inherits the page origin, so it can read the
# same localStorage and call the same-origin API endpoints.
_GOOGLE_WIDGET_TEMPLATE = """
<div id="@@UID@@" class="widget-list"><div class="widget-status">Loading...</div></div>
<script>
(function() {
  var box = document.getElementById("@@UID@@");
  var C = @@COLORS@@;
  var ENDPOINT = "@@ENDPOINT@@";
  var MAX_ROWS = @@MAX_ROWS@@;
  var TIME_FS = @@TIME_FS@@;
  var FROM_FS = @@FROM_FS@@;
  var INTERVAL = @@INTERVAL@@;
  // False until the first successful fetch. While false, errors may show a
  // status message; afterwards errors keep the shown rows — content is never
  // removed before the new data has arrived.
  var loaded = false;

  function el(tag, cls, text, style) {
    var d = document.createElement(tag);
    if (cls) d.className = cls;
    if (text != null) d.textContent = text;
    if (style) d.setAttribute("style", style);
    return d;
  }
  function status(msg) {
    box.innerHTML = "";
    box.appendChild(el("div", "widget-status", msg, "color:" + C.muted));
  }
  function readTokens() {
    try {
      var raw = null;
      try { raw = localStorage.getItem("dashboardGoogleTokens"); } catch (e) {}
      if (!raw && window.parent && window.parent !== window) {
        try { raw = window.parent.localStorage.getItem("dashboardGoogleTokens"); } catch (e) {}
      }
      var tokens = raw ? JSON.parse(raw) : null;
      if (tokens && tokens.refresh_token) return tokens;
      // Corrupt/empty entry (e.g. "[object Object]" from an older server
      // version): drop it so a fresh connect can store a clean login.
      if (raw) {
        try { localStorage.removeItem("dashboardGoogleTokens"); } catch (e) {}
        if (window.parent && window.parent !== window) {
          try { window.parent.localStorage.removeItem("dashboardGoogleTokens"); } catch (e) {}
        }
      }
      return null;
    } catch (e) { return null; }
  }
  function saveTokens(tokens) {
    try { localStorage.setItem("dashboardGoogleTokens", JSON.stringify(tokens)); return; } catch (e) {}
    if (window.parent && window.parent !== window) {
      try { window.parent.localStorage.setItem("dashboardGoogleTokens", JSON.stringify(tokens)); } catch (e) {}
    }
  }
  var API = "";
  try { API = window.parent.location.origin; } catch (e) {}
  // Relative-URL fallback: inside a sandboxed srcdoc iframe
  // location.origin is the string "null", but relative fetches still
  // resolve against the embedding page (same origin).
  if (!API || API.indexOf("http") !== 0) API = "";

  async function accessToken(tokens, force) {
    if (!force && tokens.access_token && tokens.expiryMs &&
        Date.now() < tokens.expiryMs - 60000) return tokens.access_token;
    var res = await fetch(API + "/auth/refresh", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: tokens.refresh_token })
    });
    if (!res.ok) return null;
    var data = await res.json();
    tokens.access_token = data.access_token;
    tokens.expiryMs = data.expiryMs;
    if (data.refresh_token) tokens.refresh_token = data.refresh_token;
    saveTokens(tokens);
    return tokens.access_token;
  }
  async function authedFetch() {
    var tokens = readTokens();
    if (!tokens) return { status: 0 };
    var token = await accessToken(tokens, false);
    if (!token) return { status: 401 };
    var res = await fetch(API + ENDPOINT, { headers: { "Authorization": "Bearer " + token } });
    if (res.status === 401) {
      token = await accessToken(tokens, true);
      if (!token) return { status: 401 };
      res = await fetch(API + ENDPOINT, { headers: { "Authorization": "Bearer " + token } });
    }
    return res;
  }
  function pad(n) { return (n < 10 ? "0" : "") + n; }
  function fmtStart(s) {
    var d = new Date(s);
    if (isNaN(d)) return String(s).slice(0, 10);
    return pad(d.getMonth() + 1) + "-" + pad(d.getDate()) + " " +
           pad(d.getHours()) + ":" + pad(d.getMinutes());
  }
  @@RENDER@@
  async function load() {
    var res = null;
    try {
      res = await authedFetch();
    } catch (e) {
      if (!loaded) status("Server not reachable.");
      return;
    }
    if (res.status === 0) { if (!loaded) status("Google is not connected in this browser."); return; }
    if (res.status === 401) { if (!loaded) status("Google login expired. Reconnect in Settings."); return; }
    if (!res.ok) {
      if (!loaded) {
        var msg = "Server error " + res.status;
        try { msg = (await res.json()).error || msg; } catch (e) {}
        status(msg);
      }
      return;
    }
    var data = await res.json();
    render(data.events || data.messages || []);
  }
  load();
  // The page is never re-rendered by Streamlit — each widget polls its own
  // endpoint at its own interval and swaps content only when fresh data has
  // actually arrived.
  setInterval(load, INTERVAL);
})();
</script>
"""

_GOOGLE_WIDGET_SEQ = itertools.count(1)


def _google_widget_html(colors, header_text, endpoint, max_rows, scale, kind):
    uid = "gwidget-%d" % next(_GOOGLE_WIDGET_SEQ)
    time_fs = max(int(12 * scale), 9)
    from_fs = max(int(11 * scale), 8)
    colors_json = json.dumps({
        "muted": colors["muted"],
        "text": colors["text"],
        "accent": colors["accent"],
        "header": header_text,
    })
    if kind == "calendar":
        render_js = """  function render(events) {
    loaded = true;
    var frag = document.createDocumentFragment();
    if (!events.length) {
      frag.appendChild(el("div", "widget-status", "No upcoming events", "color:" + C.muted));
    }
    events.slice(0, MAX_ROWS).forEach(function(ev) {
      var start = (ev.start && (ev.start.dateTime || ev.start.date)) || "";
      var row = el("div", "widget-list-row");
      row.appendChild(el("span", "widget-list-time", " " + (start ? fmtStart(start) : start),
        "font-size:" + TIME_FS + "px;color:" + C.header));
      row.appendChild(el("span", "widget-list-text", ev.summary || "No title",
        "font-size:" + TIME_FS + "px"));
      frag.appendChild(row);
    });
    box.innerHTML = "";
    box.appendChild(frag);
  }"""
    else:
        render_js = """  function maskAddr(a) {
    a = String(a || "").trim();
    var at = a.indexOf("@");
    return at <= 0 ? a : a.charAt(0) + "***@" + a.slice(at + 1);
  }
  function maskFrom(raw) {
    raw = String(raw || "").trim();
    if (!raw) return "(unknown sender)";
    var lt = raw.indexOf("<");
    if (lt !== -1 && raw.charAt(raw.length - 1) === ">") {
      var name = raw.slice(0, lt).trim().replace(/^"(.*)"$/, "$1").trim();
      if (name) return name;
      return maskAddr(raw.slice(lt + 1, raw.length - 1));
    }
    return maskAddr(raw);
  }
  function render(messages) {
    loaded = true;
    var frag = document.createDocumentFragment();
    if (!messages.length) {
      frag.appendChild(el("div", "widget-status", "No new messages", "color:" + C.muted));
    }
    messages.slice(0, MAX_ROWS).forEach(function(msg) {
      var unread = !!msg.unread;
      var row = el("div", "widget-msg-row");
      row.appendChild(el("span", "widget-msg-dot", unread ? "" : "",
        "font-size:" + FROM_FS + "px;color:" + (unread ? C.accent : C.muted)));
      var info = el("div", "widget-msg-info");
      info.appendChild(el("div", "widget-msg-from", maskFrom(msg.from),
        "font-size:" + FROM_FS + "px;color:" + (unread ? C.text : C.muted)));
      info.appendChild(el("div", "widget-msg-subject", msg.subject || "(no subject)",
        "font-size:" + FROM_FS + "px;color:" + C.muted));
      row.appendChild(info);
      frag.appendChild(row);
    });
    box.innerHTML = "";
    box.appendChild(frag);
  }"""
    return (
        _GOOGLE_WIDGET_TEMPLATE
        .replace("@@UID@@", uid)
        .replace("@@COLORS@@", colors_json)
        .replace("@@ENDPOINT@@", endpoint)
        .replace("@@INTERVAL@@", "300000" if kind == "calendar" else "180000")
        .replace("@@MAX_ROWS@@", str(max_rows))
        .replace("@@TIME_FS@@", str(time_fs))
        .replace("@@FROM_FS@@", str(from_fs))
        .replace("@@RENDER@@", render_js)
    )


def render_calendar_html(colors, settings, big, scale):
    header_text = get_contrast_aware_text_color(colors["widget_bg"], colors["accent"])
    max_ev = 6 if big else 3
    body = _google_widget_html(
        colors, header_text, "/calendar/events", max_ev, scale, "calendar",
    )
    return f"""
    <div class="widget-header">
        <span class="widget-header-title" style="color:{header_text}">CALENDAR</span>
    </div>
    <div class="widget-header-line" style="background:{colors['accent']}"></div>
    {body}
    """


# Stocks widget: multiple symbols (max 6) rendered as a passive price list —
# symbol, name and the live price. No +/- change, no chart, no click targets:
# a dashboard shows what things cost, not how they move. The browser refreshes
# prices via the server's /finance/price endpoint (same-origin, no key
# exposed); old values stay on screen whenever a poll fails or is in flight.
_STOCKS_WIDGET_JS = """
<script>
(function() {
  var SELECTIONS = @@SELECTIONS@@;
  var INTERVAL = @@INTERVAL@@;   // 2 min for prices; retried after 30s on fail
  var API = "";
  try { API = window.parent.location.origin; } catch (e) {}
  // Relative-URL fallback: inside a sandboxed srcdoc iframe
  // location.origin is the string "null", but relative fetches still
  // resolve against the embedding page (same origin).
  if (!API || API.indexOf("http") !== 0) API = "";

  function priceUrl(sel) {
    return API + "/finance/price?type=" + encodeURIComponent(sel.type) +
      "&symbol=" + encodeURIComponent(sel.symbol) +
      "&name=" + encodeURIComponent(sel.name);
  }
  function fmtMoney(n, frac) {
    return "$" + n.toLocaleString("en-US",
      frac ? { minimumFractionDigits: 2, maximumFractionDigits: 2 }
           : { maximumFractionDigits: 0 });
  }
  function q(sel) { return ".stocks-row[data-idx='" + sel.idx + "']"; }
  function rowFor(idx) {
    var row = document.querySelector(q({ idx: idx }));
    return row;
  }

  // ---- prices: every row updates itself only when fresh data arrives ----
  function updatePrice(idx, sel, data) {
    if (!data) return;
    var row = rowFor(idx);
    if (!row) return;
    var p = row.querySelector(".stocks-price");
    if (!p) return;
    if (data.price == null) {
      // keep the old value; only refresh a still-empty row
      if (p.textContent === "--") p.textContent = data.price_text || "Error";
      var e = row.querySelector(".stocks-err");
      if (e) e.textContent = String(data.error || "").slice(0, 40);
      return;
    }
    p.textContent = fmtMoney(Number(data.price), true);
    var e = row.querySelector(".stocks-err");
    if (e) e.textContent = "";
  }
  function pollPrice(idx, sel) {
    fetch(priceUrl(sel))
      .then(function(r) { return r.ok ? r.json() : null; })
      .then(function(d) {
        schedulePrice(30000);
        updatePrice(idx, sel, d);
      })
      .catch(function() { schedulePrice(30000); });
  }
  function schedulePrice(ms) {
    clearTimeout(priceTimer);
    priceTimer = setTimeout(function() {
      SELECTIONS.forEach(function(sel, idx) { pollPrice(idx, sel); });
    }, ms);
  }

  var priceTimer = null;
  function init() {
    schedulePrice(INTERVAL);
  }

  init();
})();
</script>
"""

_STOCKS_CSS = """
    .stocks-list { display: flex; flex-direction: column; min-height: 0; flex: 1; }
    .stocks-row { display: flex; align-items: baseline; gap: 8px; padding: 6px 10px;
                  border-radius: 10px; }
    .stocks-sym { font-weight: 700; color: @@HEADER@@; }
    .stocks-name { color: @@MUTED@@; overflow: hidden; text-overflow: ellipsis;
                   white-space: nowrap; flex: 1; }
    .stocks-price { color: @@TEXT@@; font-weight: 700; }
    .stocks-err { color: @@MUTED@@; min-width: 74px; text-align: right; }
"""


def render_stock_crypto_html(colors, settings, big, scale):
    header_text = get_contrast_aware_text_color(colors["widget_bg"], colors["accent"])
    sels = _stock_crypto_selections(settings)

    # Server-side initial prices (cached 15s per symbol, so the very first
    # frame already shows data; afterwards the browser poller updates rows).
    rows_html = []
    for idx, sel in enumerate(sels):
        result = _fetch_one_price_for_render(sel["symbol"], sel["name"], sel["type"])
        if result.get("error") or result.get("price") is None:
            price_text = result.get("price_text", "Error")
            err_text = result.get("error", "No data").replace("->", "-")[:40]
        else:
            price_text = f'${result["price"]:,.2f}'
            err_text = ""
        sym_fs = max(int((13 if big else 11) * scale), 8)
        price_fs = max(int((14 if big else 12) * scale), 9)
        rows_html.append(
            f'<div class="stocks-row" data-idx="{idx}" title="{_esc(sel["name"])} ({_esc(sel["type"])}): {_esc(sel["symbol"])}">'
            f'<span class="stocks-sym" style="font-size:{sym_fs}px">{_esc(sel["symbol"])}</span>'
            f'<span class="stocks-name" style="font-size:{sym_fs}px">{_esc(sel["name"])}</span>'
            f'<span class="stocks-price" style="font-size:{price_fs}px">{price_text}</span>'
            f'<span class="stocks-err" style="font-size:{sym_fs}px">{_esc(err_text)}</span>'
            f'</div>'
        )

    html = f"""
    <div class="widget-header">
        <span class="widget-header-title" style="color:{header_text}">STOCKS</span>
    </div>
    <div class="widget-header-line" style="background:{colors['accent']}"></div>
    <div id="stocks-rows" class="stocks-list">{''.join(rows_html)}</div>
    <div class="widget-spacer"></div>
    """
    # Client-side poller: prices every 2 min (no chart history anywhere).
    html += (
        _STOCKS_WIDGET_JS
        .replace("@@SELECTIONS@@", json.dumps([
            {"idx": i, "type": s["type"], "symbol": s["symbol"], "name": s["name"]}
            for i, s in enumerate(sels)
        ]))
        .replace("@@INTERVAL@@", "120000")
    )
    return html


def render_notifications_html(colors, settings, big, scale):
    header_text = get_contrast_aware_text_color(colors["widget_bg"], colors["accent"])
    max_msgs = 10
    body = _google_widget_html(
        colors, header_text, "/notifications/messages", max_msgs, scale, "messages",
    )
    return f"""
    <div class="widget-header">
        <span class="widget-header-title" style="color:{header_text}">MESSAGES</span>
    </div>
    <div class="widget-header-line" style="background:{colors['accent']}"></div>
    {body}
    """


# Countdown ticker: the target date is embedded at render time and the
# remaining time is computed client-side every second — no rerun needed.
_COUNTDOWN_TICKER_JS = """
<script>
(function() {
  var TARGET = @@TARGET@@;
  if (!TARGET) return;
  var target = new Date(TARGET);
  if (isNaN(target.getTime())) return;
  function pad(n) { return (n < 10 ? "0" : "") + n; }
  function tick() {
    var el = document.getElementById("cd-value");
    if (!el) return;
    var left = target.getTime() - Date.now();
    if (left <= 0) {
      el.textContent = "Reached!";
      var t = document.getElementById("cd-target");
      if (t) t.textContent = @@REACHED@@;
      return;
    }
    var s = Math.floor(left / 1000);
    var days = Math.floor(s / 86400);
    var h = Math.floor((s % 86400) / 3600);
    var m = Math.floor((s % 3600) / 60);
    el.textContent = (days > 0 ? days + "D " : "") + pad(h) + ":" + pad(m) + ":" + pad(s % 60);
  }
  tick();
  setInterval(tick, 1000);
})();
</script>
"""


def render_countdown_html(colors, settings, big, scale):
    header_text = get_contrast_aware_text_color(colors["widget_bg"], colors["accent"])
    cd = settings.get("countdown") or {}
    label_text = cd.get("label") or cd.get("name") or settings.get("countdownLabel") or settings.get("countdown_label") or "Event"
    target_date = cd.get("date") or cd.get("targetDate") or settings.get("countdownDate") or settings.get("countdown_date") or ""
    html = f"""
    <div class="widget-header">
        <span class="widget-header-title" style="color:{header_text}">COUNTDOWN</span>
    </div>
    <div class="widget-header-line" style="background:{colors['accent']}"></div>
    <div class="widget-spacer"></div>
    <div class="widget-subtitle" style="font-size:{max(int((16 if big else 13) * scale), 10)}px;color:{header_text}">{label_text}</div>
    """
    cd_fs = max(int((30 if big else 22) * scale), 12)
    date_fs = max(int(12 * scale), 9)
    target_iso = ""
    target_reached_text = ""
    if not target_date:
        html += f'<div class="widget-countdown" style="font-size:{cd_fs}px;color:{colors["text"]}">No date set</div>'
        html += f'<div class="widget-muted-text" style="font-size:{date_fs}px">Set date in Settings</div>'
    else:
        try:
            target = datetime.fromisoformat(target_date)
            if target.tzinfo is not None:
                # tz-aware date -> normalize to local naive time (same rule as
                # the Tk countdown) so the subtraction below cannot raise a
                # TypeError (naive vs aware datetime).
                target = target.astimezone().replace(tzinfo=None)
            # Local-naive ISO: JS Date parses this as local wall time, matching
            # the server-side diff below exactly.
            target_iso = target.isoformat()
            target_reached_text = target.strftime("%m-%d %Y")
            now = datetime.now()
            diff = target - now
            if diff.total_seconds() <= 0:
                html += f'<div id="cd-value" class="widget-countdown" style="font-size:{cd_fs}px;color:{colors["text"]}">Reached!</div>'
                html += f'<div id="cd-target" class="widget-muted-text" style="font-size:{date_fs}px">{target_reached_text}</div>'
            else:
                total_secs = int(diff.total_seconds())
                days = total_secs // 86400
                hours = (total_secs % 86400) // 3600
                mins = (total_secs % 3600) // 60
                secs = total_secs % 60
                if days > 0:
                    cd_text = f"{days}D {hours:02d}:{mins:02d}:{secs:02d}"
                else:
                    cd_text = f"{hours:02d}:{mins:02d}:{secs:02d}"
                html += f'<div id="cd-value" class="widget-countdown" style="font-size:{cd_fs}px;color:{colors["text"]}">{cd_text}</div>'
                html += f'<div id="cd-target" class="widget-muted-text" style="font-size:{date_fs}px">Target: {target.strftime("%m-%d %Y %H:%M")}</div>'
        except Exception:
            html += f'<div class="widget-countdown" style="font-size:{cd_fs}px;color:{colors["text"]}">Invalid date</div>'
    html += '<div class="widget-spacer"></div>'
    if target_iso:
        html += (
            _COUNTDOWN_TICKER_JS
            .replace("@@TARGET@@", json.dumps(target_iso))
            .replace("@@REACHED@@", json.dumps(target_reached_text))
        )
    return html


# Watches THIS browser's settings (localStorage, same key the settings page
# uses): when they change, reload the dashboard page once so layout/theme/
# widget changes take effect. Normal data updates (clock, countdown, weather,
# prices, calendar, messages) never reload anything — they update their own
# element in place. Server settings (settings.json) are irrelevant here: every
# browser sees its own settings only.
_SETTINGS_WATCHER_JS = """
<script>
(function() {
  var KEY = "dashboardSettings";
  var last = null;
  function read() {
    try { return localStorage.getItem(KEY); } catch (e) {}
    try {
      if (window.parent && window.parent !== window) {
        return window.parent.localStorage.getItem(KEY);
      }
    } catch (e) {}
    return null;
  }
  function trigger() {
    try { window.parent.location.reload(); return; } catch (e) {}
    try { location.reload(); } catch (e) {}
  }
  if (last === null) last = read();
  try {
    window.addEventListener("storage", function(e) {
      if (e.key === KEY || e.key === null) {
        // storage fires in OTHER tabs; ours reloads via its own poll below.
        if (read() !== last) { last = read(); trigger(); }
      }
    });
  } catch (e) {}
  setInterval(function() {
    var cur = read();
    if (cur !== last) { last = cur; trigger(); }
  }, 5000);
})();
</script>
"""

# The Streamlit page is just a bootstrap shell: it loads the browser's OWN
# settings from localStorage and fetches the real dashboard HTML via
# POST /settings/render, which renders exactly those settings on the server
# without ever touching settings.json. A fresh visitor (no saved settings)
# sees an empty dashboard with a link to the settings page — every browser
# activates its own widgets, none are inherited from the server's seed.
# Rendering client-side means every visitor only ever sees — and changes —
# their own settings, and the rendered page never flashes on any server rerun.
_BOOTSTRAP_HTML = """
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  html, body { margin: 0; height: 100%; background: #0b1220; color: #d5e2f0;
               font-family: 'Orbitron', sans-serif; }
  #boot-msg { position: fixed; inset: 0; display: flex; flex-direction: column;
              align-items: center; justify-content: center; gap: 14px;
              letter-spacing: 2px; font-size: 13px; }
  #boot-msg .bar { width: 120px; height: 3px; background: #1c2a40;
                   border-radius: 2px; overflow: hidden; }
  #boot-msg .bar i { display: block; height: 100%; width: 40%;
                     background: #3b82f6; border-radius: 2px;
                     animation: boot-slide 1.1s ease-in-out infinite; }
  @keyframes boot-slide {
    0% { margin-left: -40%; } 100% { margin-left: 100%; }
  }
  #boot-error { color: #f0876f; font-size: 11px; max-width: 70%;
                text-align: center; letter-spacing: normal; }
</style>
</head>
<body>
<div id="boot-msg">
  <span>LOADING DASHBOARD</span>
  <span class="bar"><i></i></span>
  <span id="boot-error"></span>
</div>
<script>
(function() {
  var KEY = "dashboardSettings";
  var errEl = document.getElementById("boot-error");

  // NOTE: inside the sandboxed srcdoc iframe `location.origin` is the string
  // "null" — all requests here use relative URLs, which still resolve against
  // the embedding page's origin.

  function readSaved() {
    try { return localStorage.getItem(KEY); } catch (e) {}
    try {
      if (window.parent && window.parent !== window) {
        return window.parent.localStorage.getItem(KEY);
      }
    } catch (e) {}
    return null;
  }

  function showFatal(text) {
    if (errEl) errEl.textContent = text;
  }

  // First visit in this browser: start EMPTY. Widgets are per-browser — none
  // are inherited from the server seed, so nothing is activated by default.
  // The settings watcher below reloads this page as soon as this browser
  // saves/changes its own settings.
  function showEmpty() {
    var msg = document.getElementById("boot-msg");
    if (!msg) return;
    msg.innerHTML = "";
    var title = document.createElement("span");
    title.textContent = "NO WIDGETS ENABLED YET";
    var hint = document.createElement("span");
    hint.textContent = "Widgets are private to this browser. Open the settings page to choose yours.";
    hint.style.maxWidth = "72%";
    hint.style.letterSpacing = "normal";
    hint.style.fontSize = "11px";
    hint.style.color = "#8fa3bd";
    var link = document.createElement("a");
    link.href = "/settings.html";
    link.textContent = "OPEN SETTINGS";
    link.style.cssText = "color:#3b82f6;text-decoration:none;border:1px solid #3b82f6;" +
      "padding:9px 20px;border-radius:999px;font-size:11px;letter-spacing:2px;";
    msg.appendChild(title);
    msg.appendChild(hint);
    msg.appendChild(link);
  }

  function load() {
    var body = readSaved();
    if (body) {
      render(body).catch(function() {
        showFatal("The dashboard could not be loaded. Is server.py running? Retrying...");
        setTimeout(load, 5000);
      });
    } else {
      showEmpty();
    }
  }

  function render(settingsJson) {
    return fetch("/settings/render", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: settingsJson || "{}",
    }).then(function(r) {
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.text();
    }).then(function(html) {
      document.open();
      document.write(html);
      document.close();
    });
  }

  load();
})();
</script>
"""

# The empty-state shell needs the settings watcher as well: it reloads the
# dashboard page as soon as this browser changes its (own) saved settings, so
# a first-time visitor who opens Settings and enables widgets sees the
# dashboard come alive without a manual refresh. (Plain-string template, so
# the script is concatenated rather than interpolated.)
_BOOTSTRAP_HTML += _SETTINGS_WATCHER_JS + "\n</body>\n</html>\n"


def render_dashboard_html(settings):
    """Render the full dashboard as HTML (for use under Streamlit)."""
    colors = extract_colors(settings)
    css = _inject_css(colors)

    widgets_en = settings.get("widgets", {})
    enabled = [k for k, v in widgets_en.items() if v]
    if not enabled:
        # No widgets enabled in THIS browser: show a quiet hint instead of a
        # surprise clock. Widgets are per-browser — nothing is inherited from
        # the server's seed. The embedded settings watcher below reloads this
        # page the moment this browser enables its own widgets.
        footer_loc = settings.get("location", "")
        empty_html = f"""
        <style>
            .no-widgets-hint {{ position: absolute; inset: 0; display: flex;
                flex-direction: column; align-items: center; justify-content: center;
                gap: 14px; color: {colors['text']}; }}
            .no-widgets-title {{ font-size: 15px; font-weight: 700; letter-spacing: 3px; }}
            .no-widgets-text {{ font-size: 11px; color: {colors['muted']}; max-width: 70%;
                text-align: center; letter-spacing: normal; }}
            .no-widgets-link {{ color: {colors['accent']}; text-decoration: none;
                border: 1px solid {colors['accent']}; padding: 9px 20px;
                border-radius: 999px; font-size: 11px; letter-spacing: 2px; }}
        </style>
        <div id="dashboard-header">
            <h1>DASHBOARD</h1>
            <div class="accent-line"></div>
        </div>
        <div id="dashboard-content">
            <div class="no-widgets-hint">
                <div class="no-widgets-title">NO WIDGETS ENABLED YET</div>
                <div class="no-widgets-text">Widgets are private to this browser. Open the settings page to choose yours.</div>
                <a class="no-widgets-link" href="/settings.html">OPEN SETTINGS</a>
            </div>
        </div>
        <div id="dashboard-footer">
            <span id="footer-location" style="color:{colors['muted']}">{footer_loc}</span>
        </div>
        {_SETTINGS_WATCHER_JS}
        """
        return css, empty_html
    order = settings.get("widgetOrder", [])
    ordered = [k for k in order if k in enabled]
    enabled = ordered + [k for k in enabled if k not in ordered]

    # Use a fixed content height for the web (1080px screen equivalent)
    content_h_px = max(200, 1080 - 145)
    rects = resolve_widget_layout(enabled, settings.get("widgetLayout"))
    margin = 0.006
    content_html = '<div id="dashboard-content">'

    render_map = {
        "dateTime": render_date_time_html,
        "weather": render_weather_html,
        "calendar": render_calendar_html,
        "stockCrypto": render_stock_crypto_html,
        "notifications": render_notifications_html,
        "countdown": render_countdown_html,
    }

    for key in enabled:
        rect = rects.get(key)
        if not rect:
            continue
        big = rect["h"] > 50
        area_frac = (rect["w"] / 100) * (rect["h"] / 100)
        scale = math.sqrt(area_frac / 0.10)
        card_h_px = content_h_px * rect["h"] / 100
        natural = (NATURAL_HEIGHT.get(key, 150) + (BIG_EXTRA_HEIGHT if big else 0)) * 1.10
        scale = max(0.8, min(scale, card_h_px / natural, 2.6))


        renderer = render_map.get(key)
        if not renderer:
            continue


        if key == "dateTime":
            widget_html = renderer(colors, settings, big, scale, content_h_px)
        else:
            widget_html = renderer(colors, settings, big, scale)


        left = rect["x"] / 100 + margin
        top = rect["y"] / 100 + margin
        width = rect["w"] / 100 - 2 * margin
        height = rect["h"] / 100 - 2 * margin


        card_style = (
            f"background:{colors['widget_bg']};border-color:{colors['border']};"
            f"left:{left * 100}%;top:{top * 100}%;"
            f"width:{width * 100}%;height:{height * 100}%"
        )
        content_html += f"""
        <div class="widget-card" data-key="{key}" style="{card_style}">
            {widget_html}
        </div>
        """
    content_html += "</div>"

    footer_loc = settings.get("location", "")
    footer_html = f"""
    <div id="dashboard-footer">
        <span id="footer-location" style="color:{colors['muted']}">{footer_loc}</span>
    </div>
    """

    full_html = f"""
    <div id="dashboard-header">
        <h1>DASHBOARD</h1>
        <div class="accent-line"></div>
    </div>
    {content_html}
    {footer_html}
    {_SETTINGS_WATCHER_JS}
    """

    return css, full_html


# Streamlit entry point — `server.py` launches this file with `streamlit run dashboard.py`.
# When run under Streamlit, render the HTML dashboard instead of opening Tk.
try:
    import streamlit as st
    HAS_STREAMLIT = True
except ImportError:
    HAS_STREAMLIT = False


def _running_under_streamlit() -> bool:
    """True only when THIS process is executing inside `streamlit run`.

    HAS_STREAMLIT merely says the *library* is installed. `python dashboard.py`
    (the desktop dashboard started by /launch, start_dashboard.bat, or by hand)
    also imports streamlit fine — but there is no Streamlit runtime in that
    process, so calling _run_streamlit() then would emit bare-mode warnings
    ("to view this Streamlit app on a browser, run it with ..."), never open
    the Tk window, and exit. Detect an active runtime instead.
    """
    if not HAS_STREAMLIT:
        return False

    # Primary: Streamlit >= 1.12 exposes Runtime.exists() — True exactly when
    # a runtime instance is running (i.e. we are inside `streamlit run`).
    try:
        from streamlit.runtime import Runtime
        if Runtime.exists():
            return True
    except Exception:
        pass

    # Fallback for other versions: ScriptRunContext is only present when the
    # script runs under Streamlit's runner thread.
    for module_name in (
        "streamlit.runtime.scriptrunner_utils.script_run_context",
        "streamlit.runtime.scriptrunner",
    ):
        try:
            module = __import__(module_name, fromlist=["get_script_run_ctx"])
            get_ctx = getattr(module, "get_script_run_ctx", None)
            if get_ctx is not None:
                return get_ctx() is not None
        except ImportError:
            continue
        except Exception:
            return False

    # Cannot verify a runtime -> prefer the desktop dashboard. (Under a version
    # too old/new for both checks the web path could degrade, but every
    # supported streamlit version satisfies at least one of the two checks.)
    return False


# `st.iframe` only exists in Streamlit >= 1.56; the project's requirements allow
# >= 1.40, so fall back to the (older but universal) components.v1 API there.
HAS_ST_IFRAME = HAS_STREAMLIT and hasattr(st, "iframe")


def _embed_dashboard_html(full_html: str) -> None:
    """Embed the dashboard HTML in the Streamlit page, filling the viewport.

    Uses `st.iframe` when available (Streamlit >= 1.56), otherwise the older
    `st.components.v1.html` API that ships with every Streamlit version this
    project supports. The iframe keeps our CSS isolated from Streamlit's own
    styles so Streamlit's chrome can never interfere with the dashboard.
    """
    if HAS_ST_IFRAME:
        # height="stretch" fills the whole viewport — a fixed pixel height
        # (e.g. the old height=1080) crops the dashboard on taller screens
        # and leaves a visible block of Streamlit Chrome below.
        st.iframe(full_html, height="stretch")
        return

    # Older Streamlit: scrolling on the page itself is off and the outer
    # chrome is hidden via CSS, so a full-viewport iframe fills the screen.
    html = f"""
    <style>
        html, body {{ margin: 0; padding: 0; overflow: hidden; }}
    </style>
    <iframe srcdoc={_html_attr(full_html)} style="width:100vw;height:100vh;border:0;margin:0;display:block;"
            title="Dashboard"></iframe>
    """
    st.components.v1.html(html, height=800, scrolling=False)


def _html_attr(text: str) -> str:
    """Quote text for use inside an HTML attribute, escaping the quotes that
    would otherwise terminate the attribute early."""
    return '"' + text.replace("&", "&amp;").replace('"', "&quot;").replace("\\", "&#92;") + '"'


def _run_streamlit():
    st.set_page_config(
        page_title="Dashboard",
        layout="wide",
        page_icon="favicon.png",
        initial_sidebar_state="collapsed",
    )

    # Hide Streamlit's header ("blue bar"), toolbar, deploy button, status
    # widget, sidebar and bottom block so only the dashboard shows — and
    # make the content column fill the viewport exactly, with no Streamlit
    # paddings (≈6rem top, ≈10rem bottom) and no page scrolling. The app
    # shell's DOM changed across Streamlit versions (the header moved from
    # a direct child of .stApp into the app view container, and stMain
    # turned from a <section> into a <main>), so the selectors below match
    # both generations and every rule carries !important to beat
    # Streamlit's own styles regardless of load order.
    st.markdown(
        """
        <style>
        /* 1) Hide ALL Streamlit chrome */
        .stApp > header,
        header[data-testid="stHeader"],
        [data-testid="stHeader"],
        [data-testid="stAppToolbar"],
        [data-testid="stToolbar"],
        [data-testid="stDeployButton"],
        [data-testid="stDecoration"],
        [data-testid="stStatusWidget"],
        [data-testid="stMainMenu"],
        div[data-testid="stSidebarNav"],
        [data-testid="stSidebar"],
        [data-testid="stBottom"],
        [data-testid="stBottomBlock"],
        [data-testid="stSkipToContent"] {
          display: none !important;
        }

        /* 2) Content column = full viewport, zero padding, no scrolling */
        [data-testid="stMain"], main.stMain, section.stMain,
        [data-testid="stMainBlockContainer"],
        .stMainBlockContainer, .block-container {
          height: 100vh !important;
          max-height: 100vh !important;
          height: 100dvh !important;
          max-height: 100dvh !important;
          min-height: 0 !important;
          padding: 0 !important;
          margin: 0 !important;
          max-width: none !important;
          overflow: hidden !important;
        }
        div[data-testid="stVerticalBlock"] { gap: 0 !important; }

        /* 3) Our dashboard iframe IS the whole UI. Every OTHER element
              container (e.g. the st.markdown style block) is zeroed so
              nothing above or below the iframe pushes it around or clips
              its bottom edge. Scope to [srcdoc]: only the dashboard iframe
              carries its content inline, component iframes load via src
              and must stay 0px. */
        [data-testid="stElementContainer"]:not(:has(> iframe[srcdoc])) {
          height: 0 !important;
          min-height: 0 !important;
          max-height: 0 !important;
          overflow: hidden !important;
          display: block !important;
          margin: 0 !important;
        }
        [data-testid="stElementContainer"]:has(> iframe[srcdoc]) {
          height: 100vh !important;
          min-height: 100vh !important;
          max-height: 100vh !important;
          height: 100dvh !important;
          min-height: 100dvh !important;
          max-height: 100dvh !important;
        }
        iframe[srcdoc] {
          height: 100vh !important;
          min-height: 100vh !important;
          max-height: 100vh !important;
          height: 100dvh !important;
          min-height: 100dvh !important;
          max-height: 100dvh !important;
          border: 0 !important;
          margin: 0 !important;
          padding: 0 !important;
          display: block !important;
        }

        html, body {
          margin: 0 !important;
          padding: 0 !important;
          overflow: hidden !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    # Per-browser settings — the Streamlit page itself is now only a thin,
    # static bootstrap (rendered once per page load, never rerun, so there is
    # no dim/flash). The real dashboard HTML is fetched client-side:
    #   1. the bootstrap reads THIS browser's settings from localStorage
    #      ("dashboardSettings", written by the settings page), or
    #   2. for a first visit they fall back to the server's seed via GET /load.
    # It then POSTs those settings to /settings/render, which renders the
    # dashboard for exactly that payload WITHOUT touching settings.json —
    # so every visitor only ever sees (and changes) their own settings.
    _embed_dashboard_html(_BOOTSTRAP_HTML)


if __name__ == "__main__":
    if not HAS_REQUESTS:
        print("[WARNING] 'requests' not installed. Live data will not be loaded.")
        print(" Install: pip install requests")

    settings = load_settings()
    if not settings:
        print("[INFO] No settings.json found or failed to load. Using default settings.")
        print(" Start server.py and configure it first at")
        print(" http://localhost:8000, before you start dashboard.py.")
        print(" The dashboard will run with default settings regardless.")

    # If a Streamlit runtime is active (started via `streamlit run dashboard.py`),
    # render the web dashboard; otherwise this is a direct launch — open the
    # FULLSCREEN TK dashboard on the desktop.
    if _running_under_streamlit():
        _run_streamlit()
    elif not HAS_TKINTER:
        print("[ERROR] tkinter is not installed — the desktop dashboard needs a display and python3-tk.")
        print(" Use the web dashboard instead: start server.py, then open")
        print(" http://localhost:8000/app/ (or press 'Start Dashboard' on the site).")
        sys.exit(1)
    else:
        app = Dashboard()
        app.mainloop()

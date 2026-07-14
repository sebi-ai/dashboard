import json
import os
import sys
import threading
import time
import tkinter as tk
from datetime import datetime

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

FONT_FAMILY = "Orbitron"

WEATHER_CODES = {
    0: ("Clear sky", "☀"),
    1: ("Mainly clear", "🌤"),
    2: ("Partly cloudy", "⛅"),
    3: ("Overcast", "☁"),
    45: ("Fog", "🌫"),
    48: ("Depositing rime fog", "🌫"),
    51: ("Light drizzle", "🌧"),
    53: ("Moderate drizzle", "🌧"),
    55: ("Dense drizzle", "🌧"),
    61: ("Slight rain", "🌧"),
    63: ("Moderate rain", "🌧"),
    65: ("Heavy rain", "🌧"),
    71: ("Slight snow", "❄"),
    73: ("Moderate snow", "❄"),
    75: ("Heavy snow", "❄"),
    77: ("Snow grains", "❄"),
    80: ("Slight rain showers", "🌦"),
    81: ("Moderate rain showers", "🌦"),
    82: ("Violent rain showers", "⛈"),
    85: ("Slight snow showers", "🌨"),
    86: ("Heavy snow showers", "🌨"),
    95: ("Thunderstorm", "⛈"),
    96: ("Thunderstorm with hail", "⛈"),
    99: ("Severe thunderstorm", "⛈"),
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
}

WEBSITE_THEME = {
    "bg": "#f4f7ff",
    "widget_bg": "#ffffff",
    "accent": "#0002c0",
    "text": "#071a4a",
    "border": "#0002c0",
    "muted": "#5d6c86",
    "positive": "#0a8f5b",
    "negative": "#d83a52",
}

STAR_MAP = {
    "weather-widget-star": "weather",
    "notifications-widget-star": "notifications",
"date-time-widget-star": "dateTime",
    "countdown-widget-star": "countdown",
    "calendar-widget-star":  "calendar",
    "stock-crypto-widget-star": "stockCrypto",
}

SERVER_URL = "http://localhost:8000"


def load_settings() -> dict:
    here = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(here, "settings.json")
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"[dashboard] settings.json load error: {e}")
    return {}


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
            "light": "ice",      # Helles Theme
            "dark": "midnight",  # Dunkles Theme
            "blue": "default",   # Blau (Standard)
            "green": "forest",   # Grün
            "red": "sunset",     # Rot/Orange
            "pink": "cyberpunk", # Pink/Magenta
            "purple": "midnight",# Lila
        }
        theme_key = theme_mapping.get(preset_theme, "default")
        base = THEMES.get(theme_key, THEMES["default"]).copy()

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
        super().__init__(parent, **kwargs)
        self.bg = bg
        self.border_color = border_color
        self.radius = radius
        self.configure(highlightthickness=0)
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
            radius = (x2 - x1) // 2
        if y2 - y1 < diameter:
            radius = (y2 - y1) // 2

        # Draw the filled rounded rectangle using bezier curves
        if fill:
            self._draw_rounded_polygon(x1, y1, x2, y2, radius, fill=fill)

        # Draw the border
        if outline and linewidth > 0:
            self._draw_rounded_border(x1, y1, x2, y2, radius, outline, linewidth)

    def _draw_rounded_polygon(self, x1, y1, x2, y2, r, **kwargs):
        """Draw the filled part of the rounded rectangle."""
        points = [
            x1 + r, y1,
            x2 - r, y1,
            x2, y1,
            x2, y1 + r,
            x2, y2 - r,
            x2, y2,
            x2 - r, y2,
            x1 + r, y2,
            x1, y2,
            x1, y2 - r,
            x1, y1 + r,
            x1, y1
        ]
        self.create_polygon(points, **kwargs, smooth=True)

    def _draw_rounded_border(self, x1, y1, x2, y2, r, color, width):
        """Draw the border of the rounded rectangle using arcs and lines."""
        d = 2 * r

        # Top-left to top-right
        self.create_line(x1 + r, y1, x2 - r, y1, fill=color, width=width)
        # Top-right arc
        self.create_arc(x2 - d, y1, x2, y1 + d, start=0, extent=90,
                        outline=color, width=width, style=tk.ARC)
        # Top-right to bottom-right
        self.create_line(x2, y1 + r, x2, y2 - r, fill=color, width=width)
        # Bottom-right arc
        self.create_arc(x2 - d, y2 - d, x2, y2, start=270, extent=90,
                        outline=color, width=width, style=tk.ARC)
        # Bottom-right to bottom-left
        self.create_line(x1 + r, y2, x2 - r, y2, fill=color, width=width)
        # Bottom-left arc
        self.create_arc(x1, y2 - d, x1 + d, y2, start=180, extent=90,
                        outline=color, width=width, style=tk.ARC)
        # Bottom-left to top-left
        self.create_line(x1, y1 + r, x1, y2 - r, fill=color, width=width)
        # Top-left arc
        self.create_arc(x1, y1, x1 + d, y1 + d, start=90, extent=90,
                        outline=color, width=width, style=tk.ARC)


class BaseWidget:
    REFRESH_INTERVAL = 60

    def __init__(self, parent: tk.Frame, colors: dict, big: bool = False, settings: dict = None):
        self.parent = parent
        self.colors = colors
        self.big = big
        self.settings = settings or {}
        self._alive = True

        # Create a container frame
        self.container_frame = tk.Frame(parent, bg=parent.cget("bg"))
        self.container_frame.pack(fill="both", expand=big, padx=0, pady=(0, 10))

        # Create rounded background canvas (positioned first, then content on top)
        self.bg_canvas = RoundedBackground(
            self.container_frame,
            bg=colors["widget_bg"],
            border_color=colors["border"],
            radius=30,
        )
        self.bg_canvas.pack(fill="both", expand=True)
        # bg_canvas is a tk.Canvas, where `lower()` is aliased to the
        # canvas-item `tag_lower` (needs a tag/id). Lower the *widget*
        # in the stacking order via the raw tk command instead.
        self.bg_canvas.tk.call("lower", self.bg_canvas._w)

        # Content frame on top of the canvas
        self.inner = tk.Frame(self.container_frame, bg=colors["widget_bg"])
        self.inner.pack(fill="both", expand=True, padx=14, pady=10)

        self.build()
        self._schedule_refresh()

    def header(self, icon: str, title: str):
        h = tk.Frame(self.inner, bg=self.colors["widget_bg"])
        h.pack(fill="x", pady=(0, 6))

        # Kontrastbewusste Textfarbe für Header
        widget_bg = self.colors["widget_bg"]
        accent_color = self.colors["accent"]
        header_text_color = get_contrast_aware_text_color(widget_bg, accent_color)

        tk.Label(
            h,
            text=f"{icon} {title}",
            font=(FONT_FAMILY, 10, "bold"),
            bg=self.colors["widget_bg"],
            fg=header_text_color,
        ).pack(side="left")
        tk.Frame(self.inner, height=1, bg=self.colors["border"]).pack(fill="x", pady=(0, 8))

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
        self.header("🕐", "DATE & TIME")

        time_fs = 60 if self.big else 32
        date_fs = 16 if self.big else 12

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
                font=(FONT_FAMILY, 13),
                bg=self.colors["widget_bg"], fg=self.colors["muted"],
            )
            self.lbl_day.pack(pady=(4, 0))

        self._tick()

    def _tick(self):
        now = datetime.now()
        self.lbl_time.config(text=now.strftime("%H:%M:%S"))
        self.lbl_date.config(text=now.strftime("%d. %B %Y"))
        if self.big and hasattr(self, "lbl_day"):
            self.lbl_day.config(text=now.strftime("%A"))
        self.inner.after(1000, self._tick)


class WeatherWidget(BaseWidget):
    REFRESH_INTERVAL = 600

    def build(self):
        self.header("🌤", "WEATHER")

        temp_fs = 52 if self.big else 30
        self.lbl_temp = tk.Label(
            self.inner, text="--°C",
            font=(FONT_FAMILY, temp_fs, "bold"),
            bg=self.colors["widget_bg"], fg=self.colors["text"],
        )
        self.lbl_temp.pack(pady=(6, 0))

        self.lbl_desc = tk.Label(
            self.inner, text="Loading weather data...",
            font=(FONT_FAMILY, 13 if self.big else 10),
            bg=self.colors["widget_bg"], fg=get_contrast_aware_text_color(self.colors["widget_bg"], self.colors["accent"]),
        )
        self.lbl_desc.pack(pady=(2, 4))

        if self.big:
            self.lbl_location = tk.Label(
                self.inner, text="",
                font=(FONT_FAMILY, 11),
                bg=self.colors["widget_bg"], fg=self.colors["muted"],
            )
            self.lbl_location.pack()

            self.lbl_details = tk.Label(
                self.inner, text="",
                font=(FONT_FAMILY, 11),
                bg=self.colors["widget_bg"], fg=self.colors["muted"],
            )
            self.lbl_details.pack(pady=(4, 0))

    def fetch_data(self):
        if not HAS_REQUESTS:
            return
        coords = self.settings.get("coordinates") or {}
        lat = coords.get("lat") or coords.get("latitude") or 48.137
        lon = coords.get("lon") or coords.get("longitude") or 11.575
        location_name = self.settings.get("location", "")

        try:
            r = requests.get(
                "https://api.open-meteo.com/v1/forecast",
                params={
                    "latitude": lat,
                    "longitude": lon,
                    "current": (
                        "temperature_2m,weathercode,"
                        "windspeed_10m,relative_humidity_2m,apparent_temperature"
                    ),
                    "wind_speed_unit": "kmh",
                    "timezone": "auto",
                },
                timeout=10,
            )
            r.raise_for_status()
            cur = r.json().get("current", {})

            temp = cur.get("temperature_2m", "--")
            feels = cur.get("apparent_temperature", "--")
            code = cur.get("weathercode", 0)
            wind = cur.get("windspeed_10m", "--")
            humidity = cur.get("relative_humidity_2m", "--")
            desc, icon = WEATHER_CODES.get(code, ("Unknown", "?"))

            self.lbl_temp.config(text=f"{icon} {temp}°C")
            self.lbl_desc.config(text=desc)

            if self.big:
                self.lbl_location.config(
                    text=f"📍 {location_name}" if location_name else ""
                )
                self.lbl_details.config(
                    text=(
                        f"Feels like {feels}°C • "
                        f"💨 {wind} km/h • "
                        f"💧 {humidity}%"
                    )
                )
        except Exception as exc:
            self.lbl_desc.config(text=f"Error: {str(exc)[:40]}")


class CalendarWidget(BaseWidget):
    REFRESH_INTERVAL = 300

    def build(self):
        self.header("📅", "CALENDAR")
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
                self._set_status("Google Calendar not connected.\nPlease connect in Settings.")
                return
            if r.status_code != 200:
                self._set_status(f"Server error: {r.status_code}")
                return
            events = r.json().get("events", [])
            self._render_events(events)
        except requests.exceptions.ConnectionError:
            self._set_status("Server not reachable.\n→ Start server.py")
        except Exception as exc:
            self._set_status(f"Error: {str(exc)[:50]}")

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
            summary = ev.get("summary", "No title")[:35]

            row = tk.Frame(self.list_frame, bg=self.colors["widget_bg"])
            row.pack(fill="x", pady=2)
            tk.Label(row, text=f"▸ {start_fmt}", font=(FONT_FAMILY, 10),
                    bg=self.colors["widget_bg"], fg=get_contrast_aware_text_color(self.colors["widget_bg"], self.colors["accent"]),
                    width=14, anchor="w").pack(side="left")
            tk.Label(row, text=summary, font=(FONT_FAMILY, 10),
                    bg=self.colors["widget_bg"], fg=self.colors["text"],
                    anchor="w").pack(side="left")

    def _clear(self):
        for w in self.list_frame.winfo_children():
            w.destroy()

    def _set_status(self, msg: str):
        self._clear()
        tk.Label(self.list_frame, text=msg, font=(FONT_FAMILY, 10),
                bg=self.colors["widget_bg"], fg=self.colors["muted"],
                justify="left", anchor="w").pack(fill="x")


class StockCryptoWidget(BaseWidget):
    REFRESH_INTERVAL = 120

    def build(self):
        sel = self.settings.get("stockCryptoSelection") or {}
        self._sym = sel.get("symbol", "BTC")
        self._name = sel.get("name", "Bitcoin")
        self._type = sel.get("type", "crypto")
        self._cmc_id = sel.get("id")

        icon = "₿" if self._type == "crypto" else "📈"
        self.header(icon, "PRICE")

        self.lbl_name = tk.Label(
            self.inner,
            text=f"{self._sym} — {self._name}",
            font=(FONT_FAMILY, 12 if self.big else 10, "bold"),
            bg=self.colors["widget_bg"], fg=get_contrast_aware_text_color(self.colors["widget_bg"], self.colors["accent"]),
        )
        self.lbl_name.pack(pady=(2, 0))

        price_fs = 42 if self.big else 24
        self.lbl_price = tk.Label(
            self.inner, text="-- USD",
            font=(FONT_FAMILY, price_fs, "bold"),
            bg=self.colors["widget_bg"], fg=self.colors["text"],
        )
        self.lbl_price.pack(pady=(8, 2))

        self.lbl_change = tk.Label(
            self.inner, text="",
            font=(FONT_FAMILY, 12 if self.big else 10),
            bg=self.colors["widget_bg"], fg=self.colors["muted"],
        )
        self.lbl_change.pack()

        if self.big:
            self.lbl_meta = tk.Label(
                self.inner, text="",
                font=(FONT_FAMILY, 10),
                bg=self.colors["widget_bg"], fg=self.colors["muted"],
            )
            self.lbl_meta.pack(pady=(4, 0))

    def fetch_data(self):
        if not HAS_REQUESTS:
            return
        try:
            if self._type == "crypto":
                self._fetch_crypto()
            else:
                self._fetch_stock()
        except Exception as exc:
            self.lbl_price.config(text="Error")
            self.lbl_change.config(text=str(exc)[:40], fg=self.colors["muted"])

    def _fetch_crypto(self):
        sym_lower = self._sym.lower()
        r = requests.get(
            "https://api.coingecko.com/api/v3/simple/price",
            params={
                "ids": sym_lower,
                "vs_currencies": "usd",
                "include_24hr_change": "true",
                "include_market_cap": "true",
            },
            timeout=10,
        )
        r.raise_for_status()
        data = r.json()

        coin_data = data.get(sym_lower) or (list(data.values())[0] if data else {})
        if not coin_data:
            self.lbl_price.config(text="Not found")
            return

        price = coin_data.get("usd", 0)
        change = coin_data.get("usd_24h_change", 0)
        mcap = coin_data.get("usd_market_cap", 0)

        self.lbl_price.config(text=f"${price:,.2f}")
        sign = "+" if change >= 0 else ""
        color = self.colors["positive"] if change >= 0 else self.colors["negative"]
        self.lbl_change.config(text=f"{sign}{change:.2f}% (24 h)", fg=color)
        if self.big and hasattr(self, "lbl_meta") and mcap:
            self.lbl_meta.config(text=f"Market Cap: ${mcap:,.0f}")

    def _fetch_stock(self):
        try:
            from dotenv import dotenv_values
            here = os.path.dirname(os.path.abspath(__file__))
            env = dotenv_values(os.path.join(here, ".env"))
            api_key = env.get("ALPHA_VANTAGE_API_KEY")
        except ImportError:
            api_key = None

        if api_key:
            r = requests.get(
                "https://www.alphavantage.co/query",
                params={
                    "function": "GLOBAL_QUOTE",
                    "symbol": self._sym,
                    "apikey": api_key,
                },
                timeout=10,
            )
            r.raise_for_status()
            q = r.json().get("Global Quote", {})
            price = float(q.get("05. price", 0) or 0)
            change = float(q.get("10. change percent", "0%").replace("%", "") or 0)
            self.lbl_price.config(text=f"${price:,.2f}")
            sign = "+" if change >= 0 else ""
            color = self.colors["positive"] if change >= 0 else self.colors["negative"]
            self.lbl_change.config(text=f"{sign}{change:.2f}%", fg=color)
        else:
            self.lbl_price.config(text=f"{self._sym}")
            self.lbl_change.config(
                text="Alpha Vantage Key missing in .env\n→ Open in browser",
                fg=self.colors["muted"],
            )


class NotificationsWidget(BaseWidget):
    REFRESH_INTERVAL = 180

    def build(self):
        self.header("📬", "MESSAGES")
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
                self._set_status("Gmail not connected.\nPlease connect in Settings.")
                return
            if r.status_code == 403:
                self._set_status("No Gmail permission.\nPlease reconnect your account.")
                return
            if r.status_code != 200:
                self._set_status(f"Server error: {r.status_code}")
                return
            messages = r.json().get("messages", [])
            self._render_messages(messages)
        except requests.exceptions.ConnectionError:
            self._set_status("Server not reachable.\n→ Start server.py")
        except Exception as exc:
            self._set_status(f"Error: {str(exc)[:50]}")

    def _render_messages(self, messages):
        self._clear()
        max_msg = 6 if self.big else 3
        if not messages:
            self._set_status("No new messages")
            return
        for msg in messages[:max_msg]:
            is_unread = msg.get("unread", False)
            row = tk.Frame(self.list_frame, bg=self.colors["widget_bg"])
            row.pack(fill="x", pady=2)

            dot_color = self.colors["accent"] if is_unread else self.colors["muted"]
            tk.Label(row, text="●" if is_unread else "○",
                    font=(FONT_FAMILY, 10), bg=self.colors["widget_bg"],
                    fg=dot_color, width=2).pack(side="left")

            info = tk.Frame(row, bg=self.colors["widget_bg"])
            info.pack(side="left", fill="x", expand=True)

            from_str = (msg.get("from") or "")[:28]
            subj_str = (msg.get("subject") or "(no subject)")[:38]

            tk.Label(info, text=from_str, font=(FONT_FAMILY, 9, "bold"),
                    bg=self.colors["widget_bg"],
                    fg=self.colors["text"] if is_unread else self.colors["muted"],
                    anchor="w").pack(fill="x")
            tk.Label(info, text=subj_str, font=(FONT_FAMILY, 9),
                    bg=self.colors["widget_bg"], fg=self.colors["muted"],
                    anchor="w").pack(fill="x")

    def _clear(self):
        for w in self.list_frame.winfo_children():
            w.destroy()

    def _set_status(self, msg: str):
        self._clear()
        tk.Label(self.list_frame, text=msg, font=(FONT_FAMILY, 10),
                bg=self.colors["widget_bg"], fg=self.colors["muted"],
                justify="left", anchor="w").pack(fill="x")


class CountdownWidget(BaseWidget):
    REFRESH_INTERVAL = 999999

    def build(self):
        self.header("⏳", "COUNTDOWN")

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

        self.lbl_event = tk.Label(
            self.inner, text=self._label_text,
            font=(FONT_FAMILY, 14 if self.big else 11),
            bg=self.colors["widget_bg"], fg=get_contrast_aware_text_color(self.colors["widget_bg"], self.colors["accent"]),
        )
        self.lbl_event.pack(pady=(4, 0))

        cd_fs = 32 if self.big else 20
        self.lbl_cd = tk.Label(
            self.inner, text="-- days",
            font=(FONT_FAMILY, cd_fs, "bold"),
            bg=self.colors["widget_bg"], fg=self.colors["text"],
        )
        self.lbl_cd.pack(pady=10)

        self.lbl_date = tk.Label(
            self.inner, text="",
            font=(FONT_FAMILY, 10),
            bg=self.colors["widget_bg"], fg=self.colors["muted"],
        )
        self.lbl_date.pack()

        if not self._target_date:
            self.lbl_cd.config(text="No date set")
            self.lbl_date.config(text="Set date in Settings")
        else:
            self._tick()

    def _tick(self):
        try:
            target = datetime.fromisoformat(self._target_date)
        except ValueError:
            self.lbl_cd.config(text="Invalid date")
            return

        now = datetime.now()
        diff = target - now

        if diff.total_seconds() <= 0:
            self.lbl_cd.config(text="🎉 Reached!")
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


def make_widget(parent, key, colors, big, settings):
    cls = WIDGET_CLASSES.get(key)
    if cls:
        return cls(parent, colors, big=big, settings=settings)
    tk.Label(parent, text=f"[{key}]", font=(FONT_FAMILY, 12),
            bg=colors["widget_bg"], fg=colors["muted"]).pack()


class Dashboard(tk.Tk):
    def __init__(self):
        super().__init__()
        self.settings = load_settings()
        self.colors = extract_colors(self.settings)

        self._setup_window()
        self._build_ui()

    def _setup_window(self):
        self.title("Dashboard")
        self.configure(bg=self.colors["bg"])
        self.attributes("-fullscreen", True)

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
        starred_id = self.settings.get("starredWidget", "")
        starred_key = STAR_MAP.get(starred_id, "dateTime")

        enabled = [k for k, v in widgets_en.items() if v]
        if not enabled:
            enabled = ["dateTime"]
        if starred_key not in enabled:
            starred_key = enabled[0]

        secondary = [k for k in enabled if k != starred_key][:2]

        root_frame = tk.Frame(self, bg=c["bg"])
        root_frame.pack(fill="both", expand=True, padx=22, pady=18)

        self._build_header(root_frame)

        content = tk.Frame(root_frame, bg=c["bg"])
        content.pack(fill="both", expand=True, pady=(14, 0))

        sidebar = tk.Frame(content, bg=c["bg"], width=320)
        sidebar.pack(side="left", fill="y", padx=(0, 16))
        sidebar.pack_propagate(False)

        main_area = tk.Frame(content, bg=c["bg"])
        main_area.pack(side="right", fill="both", expand=True)

        for key in secondary:
            make_widget(sidebar, key, c, big=False, settings=self.settings)

        make_widget(main_area, starred_key, c, big=True, settings=self.settings)

        self._build_footer(root_frame)

    def _build_header(self, parent):
        c = self.colors
        hdr = tk.Frame(parent, bg=c["bg"])
        hdr.pack(fill="x")

        # Kontrastbewusste Textfarbe für Dashboard-Titel
        bg_color = c["bg"]
        accent_color = c["accent"]
        header_text_color = get_contrast_aware_text_color(bg_color, accent_color)


        tk.Label(
            hdr,
            text="▣ DASHBOARD",
            font=(FONT_FAMILY, 20, "bold"),
            bg=c["bg"], fg=header_text_color,
        ).pack(side="left")

        self._hdr_clock = tk.Label(
            hdr, text="",
            font=(FONT_FAMILY, 14, "bold"),
            bg=c["bg"], fg=header_text_color,
        )
        self._hdr_clock.pack(side="right", padx=(0, 4))
        self._tick_header()
        tk.Frame(parent, height=2, bg=c["border"]).pack(fill="x", pady=(4, 0))

    def _tick_header(self):
        self._hdr_clock.config(text=datetime.now().strftime("%H:%M:%S"))
        self.after(1000, self._tick_header)

    def _build_footer(self, parent):
        c = self.colors
        tk.Frame(parent, height=1, bg=self.colors["border"]).pack(fill="x", pady=(6, 4))
        footer = tk.Frame(parent, bg=c["bg"])
        footer.pack(fill="x")

        tk.Label(
            footer,
            text="ESC Exit fullscreen F11 Fullscreen R Reload Q Quit",
            font=(FONT_FAMILY, 9),
            bg=c["bg"], fg=c["muted"],
        ).pack(side="left")

        location = self.settings.get("location", "")
        if location:
            tk.Label(
                footer,
                text=f"📍 {location}",
                font=(FONT_FAMILY, 9),
                bg=c["bg"], fg=c["muted"],
            ).pack(side="right")


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

    app = Dashboard()
    app.mainloop()


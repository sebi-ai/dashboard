import json
import math
import os
import queue
import sys
import threading
import time
import tkinter as tk
import tkinter.font as tkfont
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

SERVER_URL = "http://localhost:8000"


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

    def header(self, icon: str, title: str):
        h = tk.Frame(self.inner, bg=self.colors["widget_bg"])
        h.pack(fill="x", pady=(0, 8))

        # Kontrastbewusste Textfarbe für Header
        widget_bg = self.colors["widget_bg"]
        accent_color = self.colors["accent"]
        header_text_color = get_contrast_aware_text_color(widget_bg, accent_color)

        tk.Label(
            h,
            text=f"{icon} {title}",
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
        self.header("🕐", "DATE & TIME")

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
        self.header("🌤", "WEATHER")

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
            self.ui(lambda: self._show_weather(
                temp, feels, desc, icon, wind, humidity, location_name
            ))
        except Exception as exc:
            err = str(exc)[:40]
            self.ui(lambda: self.lbl_desc.config(text=f"Error: {err}"))

    def _show_weather(self, temp, feels, desc, icon, wind, humidity, location_name):
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
                self.ui(lambda: self._set_status("Google Calendar not connected.\nPlease connect in Settings."))
                return
            if r.status_code != 200:
                self.ui(lambda: self._set_status(f"Server error: {r.status_code}"))
                return
            events = r.json().get("events", [])
            self.ui(lambda: self._render_events(events))
        except requests.exceptions.ConnectionError:
            self.ui(lambda: self._set_status("Server not reachable.\n→ Start server.py"))
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
            summary = ev.get("summary", "No title")[:35]

            row = tk.Frame(self.list_frame, bg=self.colors["widget_bg"])
            row.pack(fill="x", pady=3)
            tk.Label(row, text=f"▸ {start_fmt}", font=(FONT_FAMILY, self.fs(12)),
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
        sel = self.settings.get("stockCryptoSelection") or {}
        self._sym = sel.get("symbol", "BTC")
        self._name = sel.get("name", "Bitcoin")
        self._type = sel.get("type", "crypto")
        self._cmc_id = sel.get("id")

        icon = "₿" if self._type == "crypto" else "📈"
        self.header(icon, "PRICE")

        tk.Frame(self.inner, bg=self.colors["widget_bg"]).pack(fill="both", expand=True)

        self.lbl_name = tk.Label(
            self.inner,
            text=f"{self._sym} — {self._name}",
            font=(FONT_FAMILY, self.fs(14 if self.big else 12), "bold"),
            bg=self.colors["widget_bg"], fg=get_contrast_aware_text_color(self.colors["widget_bg"], self.colors["accent"]),
        )
        self.lbl_name.pack(pady=(2, 0))

        price_fs = self.fs(38 if self.big else 26)
        self.lbl_price = tk.Label(
            self.inner, text="-- USD",
            font=(FONT_FAMILY, price_fs, "bold"),
            bg=self.colors["widget_bg"], fg=self.colors["text"],
        )
        self.lbl_price.pack(pady=(8, 2))

        self.lbl_change = tk.Label(
            self.inner, text="",
            font=(FONT_FAMILY, self.fs(14 if self.big else 12)),
            bg=self.colors["widget_bg"], fg=self.colors["muted"],
        )
        self.lbl_change.pack()

        if self.big:
            self.lbl_meta = tk.Label(
                self.inner, text="",
                font=(FONT_FAMILY, self.fs(12)),
                bg=self.colors["widget_bg"], fg=self.colors["muted"],
            )
            self.lbl_meta.pack(pady=(4, 0))

        tk.Frame(self.inner, bg=self.colors["widget_bg"]).pack(fill="both", expand=True)

    def fetch_data(self):
        if not HAS_REQUESTS:
            return
        try:
            r = requests.get(
                f"{SERVER_URL}/finance/price",
                params={
                    "type": self._type,
                    "symbol": self._sym,
                    "name": self._name,
                },
                timeout=10,
            )
            if r.status_code == 200:
                data = r.json()
                price = data.get("price")
                if price is None:
                    err = (data.get("error") or "No data")[:40]
                    self.ui(lambda: self._show_error(err, price_text="Unavailable"))
                    return
                self.ui(lambda: self._show_price(price, data.get("change") or 0, data.get("marketCap")))
            else:
                try:
                    err = r.json().get("error", f"HTTP {r.status_code}")
                except Exception:
                    err = f"HTTP {r.status_code}"
                self.ui(lambda: self._show_error(err[:40]))
        except requests.exceptions.ConnectionError:
            self.ui(lambda: self._show_error("→ Start server.py", price_text="Server off"))
        except Exception as exc:
            err = str(exc)[:40]
            self.ui(lambda: self._show_error(err))

    def _show_price(self, price, change, mcap):
        self.lbl_price.config(text=f"${price:,.2f}")
        sign = "+" if change >= 0 else ""
        color = self.colors["positive"] if change >= 0 else self.colors["negative"]
        self.lbl_change.config(text=f"{sign}{change:.2f}% (24 h)", fg=color)
        if self.big and hasattr(self, "lbl_meta") and mcap:
            self.lbl_meta.config(text=f"Market Cap: ${mcap:,.0f}")

    def _show_error(self, message, price_text="Error"):
        self.lbl_price.config(text=price_text)
        self.lbl_change.config(text=message, fg=self.colors["muted"])


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
                self.ui(lambda: self._set_status("Gmail not connected.\nPlease connect in Settings."))
                return
            if r.status_code == 403:
                self.ui(lambda: self._set_status("No Gmail permission.\nPlease reconnect your account."))
                return
            if r.status_code != 200:
                self.ui(lambda: self._set_status(f"Server error: {r.status_code}"))
                return
            messages = r.json().get("messages", [])
            self.ui(lambda: self._render_messages(messages))
        except requests.exceptions.ConnectionError:
            self.ui(lambda: self._set_status("Server not reachable.\n→ Start server.py"))
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
        tk.Label(row, text="●" if is_unread else "○",
                font=(FONT_FAMILY, self.fs(12)), bg=self.colors["widget_bg"],
                fg=dot_color, width=2).pack(side="left")

        info = tk.Frame(row, bg=self.colors["widget_bg"])
        info.pack(side="left", fill="x", expand=True)

        row.lbl_from = tk.Label(info, text=msg.get("from") or "(unknown sender)",
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

        The sender keeps its email address intact whenever possible: if
        "Name <address>" is too wide, only "<address>" is shown, so it never
        looks like a broken/partial address.
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
        ell = "…"
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
            text="▣ DASHBOARD",
            font=(FONT_FAMILY, 20, "bold"),
            bg=c["bg"], fg=header_text_color,
        ).pack(side="left")

        # Accent rule under the header
        tk.Frame(parent, height=2, bg=accent_color).pack(fill="x", pady=(2, 0))

    def _build_footer(self, parent):
        c = self.colors
        tk.Frame(parent, height=1, bg=self.colors["border"]).pack(fill="x", pady=(8, 5))
        footer = tk.Frame(parent, bg=c["bg"])
        footer.pack(fill="x")

        tk.Label(
            footer,
            text="ESC  exit fullscreen   •   F11  fullscreen   •   R  reload   •   Q  quit",
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


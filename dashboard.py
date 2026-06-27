"""
dashboard.py — Python-Tkinter Dashboard
Liest settings.json und zeigt die aktivierten Widgets mit den gespeicherten
Theme-Farben an. Starte zuerst server.py, damit Kalender- und
Gmail-Widgets funktionieren.

Starten:
    python3 dashboard.py

Abhängigkeiten (alle schon in requirements.txt):
    pip install requests
Optional für Wetter-Fallback ohne Koordinaten:
    pip install requests

Tastenkürzel:
    ESC       → Vollbild beenden
    F11       → Vollbild wieder aktivieren
    R         → Daten manuell neu laden
    Q         → Dashboard schließen
"""

import json
import os
import sys
import threading
import time
import tkinter as tk
from datetime import datetime
from tkinter import font as tkfont

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False


WEATHER_CODES = {
    0:  ("Klarer Himmel",      "☀"),
    1:  ("Überwiegend klar",   "🌤"),
    2:  ("Teils bewölkt",      "⛅"),
    3:  ("Bedeckt",            "☁"),
    45: ("Nebel",              "🌫"),
    48: ("Gefrierender Nebel", "🌫"),
    51: ("Leichter Niesel",    "🌧"),
    53: ("Mäßiger Niesel",     "🌧"),
    55: ("Starker Niesel",     "🌧"),
    61: ("Leichter Regen",     "🌧"),
    63: ("Mäßiger Regen",      "🌧"),
    65: ("Starker Regen",      "🌧"),
    71: ("Leichter Schnee",    "❄"),
    73: ("Mäßiger Schnee",     "❄"),
    75: ("Starker Schnee",     "❄"),
    77: ("Schneekörner",       "❄"),
    80: ("Leichte Schauer",    "🌦"),
    81: ("Mäßige Schauer",     "🌦"),
    82: ("Heftige Schauer",    "⛈"),
    85: ("Leichte Schneeschauer", "🌨"),
    86: ("Starke Schneeschauer",  "🌨"),
    95: ("Gewitter",           "⛈"),
    96: ("Gewitter m. Hagel",  "⛈"),
    99: ("Starkes Gewitter",   "⛈"),
}


THEMES = {
    "default": {
        "bg":         "#0d0d1a",
        "widget_bg":  "#16162a",
        "accent":     "#00d4ff",
        "text":       "#e0e0ff",
        "border":     "#2a2a50",
        "muted":      "#6666aa",
        "positive":   "#00ff88",
        "negative":   "#ff4466",
    },
    "ocean": {
        "bg":         "#080e1a",
        "widget_bg":  "#0f1e30",
        "accent":     "#00b4d8",
        "text":       "#caf0f8",
        "border":     "#1a3050",
        "muted":      "#5588aa",
        "positive":   "#00e5b0",
        "negative":   "#ff5555",
    },
    "forest": {
        "bg":         "#080f08",
        "widget_bg":  "#0f1e12",
        "accent":     "#52b788",
        "text":       "#d8f3dc",
        "border":     "#1e3d25",
        "muted":      "#558866",
        "positive":   "#74c69d",
        "negative":   "#ff6b6b",
    },
    "sunset": {
        "bg":         "#180800",
        "widget_bg":  "#261200",
        "accent":     "#ff7b35",
        "text":       "#ffe8d6",
        "border":     "#552200",
        "muted":      "#aa6644",
        "positive":   "#ffbb44",
        "negative":   "#ff3333",
    },
    "cyberpunk": {
        "bg":         "#080010",
        "widget_bg":  "#10001e",
        "accent":     "#ff00ff",
        "text":       "#00ffff",
        "border":     "#3a0060",
        "muted":      "#882288",
        "positive":   "#00ff88",
        "negative":   "#ff2244",
    },
    "ice": {
        "bg":         "#080816",
        "widget_bg":  "#12182a",
        "accent":     "#90caf9",
        "text":       "#e8f4ff",
        "border":     "#1e2e48",
        "muted":      "#4466aa",
        "positive":   "#66ddff",
        "negative":   "#ff6688",
    },
    "midnight": {
        "bg":         "#030008",
        "widget_bg":  "#0a0018",
        "accent":     "#9b59b6",
        "text":       "#dda0ff",
        "border":     "#25004a",
        "muted":      "#6a308a",
        "positive":   "#a855f7",
        "negative":   "#ff4488",
    },
}

STAR_MAP = {
    "weather-widget-star":      "weather",
    "notifications-widget-star": "notifications",
    "date-time-widget-star":    "dateTime",
    "countdown-widget-star":    "countdown",
    "calendar-widget-star":     "calendar",
    "stock-crypto-widget-star": "stockCrypto",
}

SERVER_URL = "http://localhost:8000"




def load_settings() -> dict:
    """Lädt settings.json aus dem gleichen Verzeichnis wie dashboard.py."""
    here = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(here, "settings.json")
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"[dashboard] settings.json Ladefehler: {e}")
    return {}


def extract_colors(settings: dict) -> dict:
    """
    Liest Farbwerte aus settings.json.
    Unterstützt: theme-Name, primaryColor / accentColor / customColor / backgroundColor.
    Fällt auf das Default-Theme zurück, wenn keine Farben gesetzt sind.
    """
    theme_name = settings.get("theme", "default")
    base = THEMES.get(theme_name, THEMES["default"]).copy()

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
        "text":   settings.get("textColor"),
        "widget_bg": (
            settings.get("widgetBgColor")
            or settings.get("cardColor")
            or settings.get("cardBgColor")
        ),
        "border": settings.get("borderColor"),
        "muted":  settings.get("secondaryTextColor") or settings.get("mutedColor"),
    }
    for key, val in overrides.items():
        if val and isinstance(val, str) and val.startswith("#"):
            base[key] = val

    return base


def run_in_thread(func, *args, daemon=True):
    t = threading.Thread(target=func, args=args, daemon=daemon)
    t.start()
    return t


class BaseWidget:
    """Jedes Widget erbt hiervon und implementiert build() und fetch_data()."""

    REFRESH_INTERVAL = 60  

    def __init__(self, parent: tk.Frame, colors: dict, big: bool = False, settings: dict = None):
        self.parent   = parent
        self.colors   = colors
        self.big      = big
        self.settings = settings or {}
        self._alive   = True

        self.frame = tk.Frame(
            parent,
            bg=colors["widget_bg"],
            highlightbackground=colors["border"],
            highlightthickness=1,
        )
        self.frame.pack(fill="both", expand=big, padx=0, pady=(0, 10))

        self.inner = tk.Frame(self.frame, bg=colors["widget_bg"])
        self.inner.pack(fill="both", expand=True, padx=14, pady=10)

        self.build()
        self._schedule_refresh()

    
    def header(self, icon: str, title: str):
        h = tk.Frame(self.inner, bg=self.colors["widget_bg"])
        h.pack(fill="x", pady=(0, 6))
        tk.Label(
            h,
            text=f"{icon}  {title}",
            font=("Courier", 10, "bold"),
            bg=self.colors["widget_bg"],
            fg=self.colors["accent"],
        ).pack(side="left")
        tk.Frame(self.inner, height=1, bg=self.colors["border"]).pack(fill="x", pady=(0, 8))

    def label(self, parent, text="", font_size=12, bold=False, color_key="text", anchor="center") -> tk.Label:
        weight = "bold" if bold else "normal"
        lbl = tk.Label(
            parent,
            text=text,
            font=("Courier", font_size, weight),
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
            font=("Courier", font_size),
            bg=self.colors["widget_bg"],
            fg=self.colors["muted"],
            anchor=anchor,
        )
        lbl.pack(fill="x" if anchor == "w" else None)
        return lbl

    def build(self):
        """Erstellt das Widget-Layout. Muss überschrieben werden."""

    def fetch_data(self):
        """Holt Daten und aktualisiert Labels. Läuft im Hintergrund-Thread."""

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

        time_fs  = 60 if self.big else 32
        date_fs  = 16 if self.big else 12

        self.lbl_time = tk.Label(
            self.inner, text="--:--:--",
            font=("Courier", time_fs, "bold"),
            bg=self.colors["widget_bg"], fg=self.colors["text"],
        )
        self.lbl_time.pack(pady=(6, 2))

        self.lbl_date = tk.Label(
            self.inner, text="",
            font=("Courier", date_fs),
            bg=self.colors["widget_bg"], fg=self.colors["accent"],
        )
        self.lbl_date.pack()

        if self.big:
            self.lbl_day = tk.Label(
                self.inner, text="",
                font=("Courier", 13),
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
        self.header("🌤", "WETTER")

        temp_fs = 52 if self.big else 30
        self.lbl_temp = tk.Label(
            self.inner, text="--°C",
            font=("Courier", temp_fs, "bold"),
            bg=self.colors["widget_bg"], fg=self.colors["text"],
        )
        self.lbl_temp.pack(pady=(6, 0))

        self.lbl_desc = tk.Label(
            self.inner, text="Lade Wetterdaten …",
            font=("Courier", 13 if self.big else 10),
            bg=self.colors["widget_bg"], fg=self.colors["accent"],
        )
        self.lbl_desc.pack(pady=(2, 4))

        if self.big:
            self.lbl_location = tk.Label(
                self.inner, text="",
                font=("Courier", 11),
                bg=self.colors["widget_bg"], fg=self.colors["muted"],
            )
            self.lbl_location.pack()

            self.lbl_details = tk.Label(
                self.inner, text="",
                font=("Courier", 11),
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
                    "latitude":  lat,
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

            temp     = cur.get("temperature_2m", "--")
            feels    = cur.get("apparent_temperature", "--")
            code     = cur.get("weathercode", 0)
            wind     = cur.get("windspeed_10m", "--")
            humidity = cur.get("relative_humidity_2m", "--")
            desc, icon = WEATHER_CODES.get(code, ("Unbekannt", "?"))

            self.lbl_temp.config(text=f"{icon} {temp}°C")
            self.lbl_desc.config(text=desc)

            if self.big:
                self.lbl_location.config(
                    text=f"📍 {location_name}" if location_name else ""
                )
                self.lbl_details.config(
                    text=(
                        f"Gefühlt {feels}°C  •  "
                        f"💨 {wind} km/h  •  "
                        f"💧 {humidity}%"
                    )
                )
        except Exception as exc:
            self.lbl_desc.config(text=f"Fehler: {str(exc)[:40]}")



class CalendarWidget(BaseWidget):
    REFRESH_INTERVAL = 300  

    def build(self):
        self.header("📅", "KALENDER")
        self.list_frame = tk.Frame(self.inner, bg=self.colors["widget_bg"])
        self.list_frame.pack(fill="both", expand=True)
        self._set_status("Kalender wird geladen …")

    def fetch_data(self):
        if not HAS_REQUESTS:
            self._set_status("requests nicht installiert")
            return
        try:
            r = requests.get(f"{SERVER_URL}/calendar/events", timeout=6)
            if r.status_code == 401:
                self._set_status("Google Kalender nicht verbunden.\nBitte in den Einstellungen verbinden.")
                return
            if r.status_code != 200:
                self._set_status(f"Serverfehler: {r.status_code}")
                return
            events = r.json().get("events", [])
            self._render_events(events)
        except requests.exceptions.ConnectionError:
            self._set_status("Server nicht erreichbar.\n→ server.py starten")
        except Exception as exc:
            self._set_status(f"Fehler: {str(exc)[:50]}")

    def _render_events(self, events):
        self._clear()
        max_ev = 6 if self.big else 3
        if not events:
            self._set_status("Keine bevorstehenden Termine")
            return
        for ev in events[:max_ev]:
            start_raw = (ev.get("start") or {}).get("dateTime") or (ev.get("start") or {}).get("date", "")
            try:
                dt = datetime.fromisoformat(start_raw.replace("Z", "+00:00"))
                start_fmt = dt.strftime("%d.%m  %H:%M")
            except Exception:
                start_fmt = start_raw[:10]
            summary = ev.get("summary", "Ohne Titel")[:35]

            row = tk.Frame(self.list_frame, bg=self.colors["widget_bg"])
            row.pack(fill="x", pady=2)
            tk.Label(row, text=f"▸ {start_fmt}", font=("Courier", 10),
                    bg=self.colors["widget_bg"], fg=self.colors["accent"],
                    width=14, anchor="w").pack(side="left")
            tk.Label(row, text=summary, font=("Courier", 10),
                    bg=self.colors["widget_bg"], fg=self.colors["text"],
                    anchor="w").pack(side="left")

    def _clear(self):
        for w in self.list_frame.winfo_children():
            w.destroy()

    def _set_status(self, msg: str):
        self._clear()
        tk.Label(self.list_frame, text=msg, font=("Courier", 10),
                bg=self.colors["widget_bg"], fg=self.colors["muted"],
                justify="left", anchor="w").pack(fill="x")


class StockCryptoWidget(BaseWidget):
    REFRESH_INTERVAL = 120  

    def build(self):
        sel  = self.settings.get("stockCryptoSelection") or {}
        self._sym  = sel.get("symbol", "BTC")
        self._name = sel.get("name", "Bitcoin")
        self._type = sel.get("type", "crypto")
        self._cmc_id = sel.get("id")

        icon = "₿" if self._type == "crypto" else "📈"
        self.header(icon, "KURS")

        self.lbl_name = tk.Label(
            self.inner,
            text=f"{self._sym}  —  {self._name}",
            font=("Courier", 12 if self.big else 10, "bold"),
            bg=self.colors["widget_bg"], fg=self.colors["accent"],
        )
        self.lbl_name.pack(pady=(2, 0))

        price_fs = 42 if self.big else 24
        self.lbl_price = tk.Label(
            self.inner, text="-- USD",
            font=("Courier", price_fs, "bold"),
            bg=self.colors["widget_bg"], fg=self.colors["text"],
        )
        self.lbl_price.pack(pady=(8, 2))

        self.lbl_change = tk.Label(
            self.inner, text="",
            font=("Courier", 12 if self.big else 10),
            bg=self.colors["widget_bg"], fg=self.colors["muted"],
        )
        self.lbl_change.pack()

        if self.big:
            self.lbl_meta = tk.Label(
                self.inner, text="",
                font=("Courier", 10),
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
            self.lbl_price.config(text="Fehler")
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
            self.lbl_price.config(text="Nicht gefunden")
            return

        price  = coin_data.get("usd", 0)
        change = coin_data.get("usd_24h_change", 0)
        mcap   = coin_data.get("usd_market_cap", 0)

        self.lbl_price.config(text=f"${price:,.2f}")
        sign  = "+" if change >= 0 else ""
        color = self.colors["positive"] if change >= 0 else self.colors["negative"]
        self.lbl_change.config(text=f"{sign}{change:.2f}%  (24 h)", fg=color)
        if self.big and hasattr(self, "lbl_meta") and mcap:
            self.lbl_meta.config(text=f"Market Cap: ${mcap:,.0f}")

    def _fetch_stock(self):
        try:
            from dotenv import dotenv_values
            here = os.path.dirname(os.path.abspath(__file__))
            env  = dotenv_values(os.path.join(here, ".env"))
            api_key = env.get("ALPHA_VANTAGE_API_KEY")
        except ImportError:
            api_key = None

        if api_key:
            r = requests.get(
                "https://www.alphavantage.co/query",
                params={
                    "function": "GLOBAL_QUOTE",
                    "symbol":   self._sym,
                    "apikey":   api_key,
                },
                timeout=10,
            )
            r.raise_for_status()
            q = r.json().get("Global Quote", {})
            price  = float(q.get("05. price", 0) or 0)
            change = float(q.get("10. change percent", "0%").replace("%", "") or 0)
            self.lbl_price.config(text=f"${price:,.2f}")
            sign  = "+" if change >= 0 else ""
            color = self.colors["positive"] if change >= 0 else self.colors["negative"]
            self.lbl_change.config(text=f"{sign}{change:.2f}%", fg=color)
        else:
            self.lbl_price.config(text=f"{self._sym}")
            self.lbl_change.config(
                text="Alpha Vantage Key fehlt in .env\n→ browser öffnen",
                fg=self.colors["muted"],
            )


class NotificationsWidget(BaseWidget):
    REFRESH_INTERVAL = 180  

    def build(self):
        self.header("📬", "NACHRICHTEN")
        self.list_frame = tk.Frame(self.inner, bg=self.colors["widget_bg"])
        self.list_frame.pack(fill="both", expand=True)
        self._set_status("Nachrichten werden geladen …")

    def fetch_data(self):
        if not HAS_REQUESTS:
            self._set_status("requests nicht installiert")
            return
        try:
            r = requests.get(f"{SERVER_URL}/notifications/messages", timeout=8)
            if r.status_code == 401:
                self._set_status("Gmail nicht verbunden.\nBitte in den Einstellungen verbinden.")
                return
            if r.status_code == 403:
                self._set_status("Keine Gmail-Berechtigung.\nBitte Konto neu verbinden.")
                return
            if r.status_code != 200:
                self._set_status(f"Serverfehler: {r.status_code}")
                return
            messages = r.json().get("messages", [])
            self._render_messages(messages)
        except requests.exceptions.ConnectionError:
            self._set_status("Server nicht erreichbar.\n→ server.py starten")
        except Exception as exc:
            self._set_status(f"Fehler: {str(exc)[:50]}")

    def _render_messages(self, messages):
        self._clear()
        max_msg = 6 if self.big else 3
        if not messages:
            self._set_status("Keine neuen Nachrichten")
            return
        for msg in messages[:max_msg]:
            is_unread = msg.get("unread", False)
            row = tk.Frame(self.list_frame, bg=self.colors["widget_bg"])
            row.pack(fill="x", pady=2)

            dot_color = self.colors["accent"] if is_unread else self.colors["muted"]
            tk.Label(row, text="●" if is_unread else "○",
                    font=("Courier", 10), bg=self.colors["widget_bg"],
                    fg=dot_color, width=2).pack(side="left")

            info = tk.Frame(row, bg=self.colors["widget_bg"])
            info.pack(side="left", fill="x", expand=True)

            from_str = (msg.get("from") or "")[:28]
            subj_str = (msg.get("subject") or "(kein Betreff)")[:38]

            tk.Label(info, text=from_str, font=("Courier", 9, "bold"),
                    bg=self.colors["widget_bg"],
                    fg=self.colors["text"] if is_unread else self.colors["muted"],
                    anchor="w").pack(fill="x")
            tk.Label(info, text=subj_str, font=("Courier", 9),
                    bg=self.colors["widget_bg"], fg=self.colors["muted"],
                    anchor="w").pack(fill="x")

    def _clear(self):
        for w in self.list_frame.winfo_children():
            w.destroy()

    def _set_status(self, msg: str):
        self._clear()
        tk.Label(self.list_frame, text=msg, font=("Courier", 10),
                bg=self.colors["widget_bg"], fg=self.colors["muted"],
                justify="left", anchor="w").pack(fill="x")


class CountdownWidget(BaseWidget):
    REFRESH_INTERVAL = 999999

    def build(self):
        self.header("⏳", "COUNTDOWN")

        cd = self.settings.get("countdown") or {}
        self._label_text  = cd.get("label") or cd.get("name") or "Event"
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
            font=("Courier", 14 if self.big else 11),
            bg=self.colors["widget_bg"], fg=self.colors["accent"],
        )
        self.lbl_event.pack(pady=(4, 0))

        cd_fs = 32 if self.big else 20
        self.lbl_cd = tk.Label(
            self.inner, text="-- Tage",
            font=("Courier", cd_fs, "bold"),
            bg=self.colors["widget_bg"], fg=self.colors["text"],
        )
        self.lbl_cd.pack(pady=10)

        self.lbl_date = tk.Label(
            self.inner, text="",
            font=("Courier", 10),
            bg=self.colors["widget_bg"], fg=self.colors["muted"],
        )
        self.lbl_date.pack()

        if not self._target_date:
            self.lbl_cd.config(text="Kein Datum")
            self.lbl_date.config(text="Datum in den Einstellungen setzen")
        else:
            self._tick()

    def _tick(self):
        try:
            target = datetime.fromisoformat(self._target_date)
        except ValueError:
            self.lbl_cd.config(text="Ungültiges Datum")
            return

        now  = datetime.now()
        diff = target - now

        if diff.total_seconds() <= 0:
            self.lbl_cd.config(text="🎉 Erreicht!")
            self.lbl_date.config(text=target.strftime("%d.%m.%Y"))
            return

        total_secs = int(diff.total_seconds())
        days  = total_secs // 86400
        hours = (total_secs % 86400) // 3600
        mins  = (total_secs % 3600)  // 60
        secs  = total_secs % 60

        if days > 0:
            self.lbl_cd.config(text=f"{days}T  {hours:02d}:{mins:02d}:{secs:02d}")
        else:
            self.lbl_cd.config(text=f"{hours:02d}:{mins:02d}:{secs:02d}")

        self.lbl_date.config(text=target.strftime("Ziel: %d.%m.%Y  %H:%M"))
        self.inner.after(1000, self._tick)


WIDGET_CLASSES = {
    "dateTime":    DateTimeWidget,
    "weather":     WeatherWidget,
    "calendar":    CalendarWidget,
    "stockCrypto": StockCryptoWidget,
    "notifications": NotificationsWidget,
    "countdown":   CountdownWidget,
}


def make_widget(parent, key, colors, big, settings):
    cls = WIDGET_CLASSES.get(key)
    if cls:
        return cls(parent, colors, big=big, settings=settings)
    tk.Label(parent, text=f"[{key}]", font=("Courier", 12),
            bg=colors["widget_bg"], fg=colors["muted"]).pack()


class Dashboard(tk.Tk):
    def __init__(self):
        super().__init__()
        self.settings = load_settings()
        self.colors   = extract_colors(self.settings)

        self._setup_window()
        self._build_ui()

    def _setup_window(self):
        self.title("Dashboard")
        self.configure(bg=self.colors["bg"])
        self.attributes("-fullscreen", True)

        self.bind("<Escape>", lambda e: self.attributes("-fullscreen", False))
        self.bind("<F11>",    lambda e: self.attributes("-fullscreen", True))
        self.bind("<q>",      lambda e: self.destroy())
        self.bind("<Q>",      lambda e: self.destroy())
        self.bind("<r>",      lambda e: self._soft_reload())
        self.bind("<R>",      lambda e: self._soft_reload())

    def _soft_reload(self):
        """Neustart des Dashboards mit frisch geladenen Einstellungen."""
        self.destroy()
        python = sys.executable
        os.execl(python, python, *sys.argv)
    def _build_ui(self):
        c          = self.colors
        widgets_en = self.settings.get("widgets") or {}
        starred_id = self.settings.get("starredWidget", "")
        starred_key = STAR_MAP.get(starred_id, "dateTime")

        enabled = [k for k, v in widgets_en.items() if v]
        if not enabled:
            enabled = ["dateTime"]
        if starred_key not in enabled:
            starred_key = enabled[0]

        secondary = [k for k in enabled if k != starred_key]

        root_frame = tk.Frame(self, bg=c["bg"])
        root_frame.pack(fill="both", expand=True, padx=18, pady=14)

        self._build_header(root_frame)
        content = tk.Frame(root_frame, bg=c["bg"])
        content.pack(fill="both", expand=True, pady=(8, 0))

        left = tk.Frame(content, bg=c["bg"])
        left.pack(side="left", fill="both", expand=True, padx=(0, 10))
        make_widget(left, starred_key, c, big=True, settings=self.settings)
        if secondary:
            right = tk.Frame(content, bg=c["bg"], width=340)
            right.pack(side="right", fill="both")
            right.pack_propagate(False)
            for key in secondary[:3]:
                make_widget(right, key, c, big=False, settings=self.settings)

        self._build_footer(root_frame)

    def _build_header(self, parent):
        c = self.colors
        hdr = tk.Frame(parent, bg=c["bg"])
        hdr.pack(fill="x")

        tk.Label(
            hdr,
            text="▣  DASHBOARD",
            font=("Courier", 20, "bold"),
            bg=c["bg"], fg=c["accent"],
        ).pack(side="left")

        self._hdr_clock = tk.Label(
            hdr, text="",
            font=("Courier", 14, "bold"),
            bg=c["bg"], fg=c["accent"],
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
            text="ESC Vollbild verlassen   F11 Vollbild   R Neu laden   Q Beenden",
            font=("Courier", 9),
            bg=c["bg"], fg=c["muted"],
        ).pack(side="left")

        location = self.settings.get("location", "")
        if location:
            tk.Label(
                footer,
                text=f"📍 {location}",
                font=("Courier", 9),
                bg=c["bg"], fg=c["muted"],
            ).pack(side="right")


if __name__ == "__main__":
    if not HAS_REQUESTS:
        print("[WARNUNG] 'requests' nicht installiert. Live-Daten werden nicht geladen.")
        print("          Installieren: pip install requests")

    settings = load_settings()
    if not settings:
        print("[INFO] No settings.json found or failed to load. Using default settings.")
        print("       Start server.py and configure it first at")
        print("       http://localhost:8000, before you start dashboard.py.")
        print("       The dashboard will run with default settings regardless.")

    app = Dashboard()
    app.mainloop()
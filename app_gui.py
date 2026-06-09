from __future__ import annotations

import sys
import threading
from datetime import datetime
from zoneinfo import ZoneInfo

import requests
from PySide6 import QtCore, QtWidgets, QtGui

APP_TITLE = "Stardance Dashboard (Native)"
DEFAULT_TIMEZONE = "Europe/Berlin"


WEATHER_CODE_MAP = {
    0: ("Clear sky", "☀️"),
    1: ("Mainly clear", "🌤️"),
    2: ("Partly cloudy", "⛅"),
    3: ("Cloudy", "☁️"),
    45: ("Fog", "🌫️"),
    48: ("Depositing rime fog", "🌫️"),
    51: ("Light drizzle", "🌦️"),
    53: ("Drizzle", "🌦️"),
    55: ("Dense drizzle", "🌧️"),
    61: ("Slight rain", "🌦️"),
    63: ("Rain", "🌧️"),
    65: ("Heavy rain", "🌧️"),
    66: ("Freezing rain", "🧊"),
    67: ("Heavy freezing rain", "🧊"),
    71: ("Slight snow fall", "🌨️"),
    73: ("Snow fall", "🌨️"),
    75: ("Heavy snow fall", "❄️"),
    77: ("Snow grains", "🌨️"),
    80: ("Slight rain showers", "🌦️"),
    81: ("Rain showers", "🌧️"),
    82: ("Violent rain showers", "⛈️"),
    85: ("Slight snow showers", "🌨️"),
    86: ("Heavy snow showers", "❄️"),
    95: ("Thunderstorm", "⛈️"),
    96: ("Thunderstorm with hail", "⛈️"),
    99: ("Heavy thunderstorm with hail", "⛈️"),
}


def weather_label(code: int) -> tuple[str, str]:
    return WEATHER_CODE_MAP.get(code, (f"Weather code {code}", "🌡️"))


def fetch_location() -> dict:
    response = requests.get("https://ipwho.is/", timeout=10)
    response.raise_for_status()
    data = response.json()
    if not data.get("success", False):
        raise RuntimeError(data.get("message", "Location data could not be loaded."))

    return {
        "city": data.get("city") or "Unbekannt",
        "region": data.get("region") or "",
        "country": data.get("country") or "",
        "latitude": data["latitude"],
        "longitude": data["longitude"],
        "timezone": data.get("timezone", {}).get("id") or DEFAULT_TIMEZONE,
        "ip": data.get("ip", ""),
    }


def fetch_weather(latitude: float, longitude: float, timezone: str) -> dict:
    url = (
        "https://api.open-meteo.com/v1/forecast"
        f"?latitude={latitude}&longitude={longitude}"
        "&current=temperature_2m,relative_humidity_2m,apparent_temperature,weather_code,wind_speed_10m"
        f"&timezone={timezone}"
    )
    response = requests.get(url, timeout=10)
    response.raise_for_status()
    return response.json()


class FetchThread(QtCore.QThread):
    data_ready = QtCore.Signal(object)
    error = QtCore.Signal(str)

    def run(self) -> None:  # pragma: no cover - network
        try:
            location = fetch_location()
            weather = fetch_weather(location["latitude"], location["longitude"], location["timezone"])
            self.data_ready.emit({"location": location, "weather": weather})
        except Exception as e:
            self.error.emit(str(e))


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(APP_TITLE)
        self.resize(1000, 600)

        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        main_layout = QtWidgets.QHBoxLayout(central)
        main_layout.setStretch(0, 2)
        main_layout.setStretch(1, 1)

        # Left: big clock
        self.left_frame = QtWidgets.QFrame()
        self.left_frame.setObjectName("glassCard")
        self.left_frame.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Expanding)
        left_layout = QtWidgets.QVBoxLayout(self.left_frame)
        left_layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        left_layout.setSpacing(8)

        self.time_title = QtWidgets.QLabel("Time")
        self.time_title.setStyleSheet("color: rgba(255,255,255,0.72); font-size: 12px; font-weight: 700; letter-spacing: 0.08em; text-transform: uppercase;")
        left_layout.addWidget(self.time_title)

        self.time_label = QtWidgets.QLabel("--:--:--")
        time_font = QtGui.QFont("Segoe UI", 96, QtGui.QFont.Weight.Bold)
        self.time_label.setFont(time_font)
        self.time_label.setStyleSheet("color: rgba(255,255,255,0.9);")
        self.time_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        left_layout.addWidget(self.time_label)

        self.date_label = QtWidgets.QLabel("—")
        date_font = QtGui.QFont("Segoe UI", 12)
        self.date_label.setFont(date_font)
        self.date_label.setStyleSheet("color: rgba(255,255,255,0.78);")
        left_layout.addWidget(self.date_label)

        main_layout.addWidget(self.left_frame, 2)

        # Right: compact weather summary
        right_frame = QtWidgets.QFrame()
        right_frame.setMinimumWidth(320)
        right_frame.setSizePolicy(QtWidgets.QSizePolicy.Policy.Preferred, QtWidgets.QSizePolicy.Policy.Expanding)
        right_layout = QtWidgets.QVBoxLayout(right_frame)

        # Weather card
        card = QtWidgets.QFrame()
        card.setObjectName("glassCard")
        card_layout = QtWidgets.QVBoxLayout(card)

        weather_title = QtWidgets.QLabel("Weather")
        weather_title.setStyleSheet("color: rgba(255,255,255,0.72); font-size: 12px; font-weight: 700; letter-spacing: 0.08em; text-transform: uppercase;")
        card_layout.addWidget(weather_title)

        self.location_label = QtWidgets.QLabel("Location: —")
        self.location_label.setStyleSheet("color: rgba(255,255,255,0.9); font-weight:600;")
        card_layout.addWidget(self.location_label)

        self.weather_main = QtWidgets.QLabel("—")
        weather_font = QtGui.QFont("Segoe UI", 18, QtGui.QFont.Weight.DemiBold)
        self.weather_main.setFont(weather_font)
        card_layout.addWidget(self.weather_main)

        self.now_label = QtWidgets.QLabel("—")
        now_font = QtGui.QFont("Segoe UI", 32, QtGui.QFont.Weight.Bold)
        self.now_label.setFont(now_font)
        self.now_label.setStyleSheet("color: rgba(255,255,255,0.85);")
        card_layout.addWidget(self.now_label)

        self.feels_label = QtWidgets.QLabel("Feels like: —")
        feels_font = QtGui.QFont("Segoe UI", 11)
        self.feels_label.setFont(feels_font)
        self.feels_label.setStyleSheet("color: rgba(255,255,255,0.65);")
        card_layout.addWidget(self.feels_label)

        self.wind_label = QtWidgets.QLabel("Wind: — | Humidity: —")
        self.wind_label.setStyleSheet("color: rgba(255,255,255,0.75);")
        card_layout.addWidget(self.wind_label)

        right_layout.addWidget(card)

        right_layout.addStretch()

        # status
        self.status = QtWidgets.QLabel("")
        self.status.setStyleSheet("color: rgba(255,255,255,0.65); font-size: 12px;")
        right_layout.addWidget(self.status)

        main_layout.addWidget(right_frame, 1)

        # global stylesheet for modern look
        self.setStyleSheet("""
        QMainWindow { background: qlineargradient(spread:pad, x1:0, y1:0, x2:1, y2:1, stop:0 #041018, stop:1 #071526); }
        #glassCard { background: rgba(255,255,255,0.04); border-radius: 12px; padding: 12px; border: 1px solid rgba(255,255,255,0.06); }
        QTableWidget { background: rgba(255,255,255,0.02); color: rgba(234,242,255,0.95); border-radius: 8px; }
        QHeaderView::section { background: transparent; color: rgba(255,255,255,0.72); }
        """)

        self.setStatusBar(QtWidgets.QStatusBar(self))
        self.statusBar().setSizeGripEnabled(False)
        self.statusBar().hide()

        # timers
        self.time_zone = DEFAULT_TIMEZONE
        self.local_now = datetime.now(ZoneInfo(self.time_zone))

        self.clock_timer = QtCore.QTimer(self)
        self.clock_timer.timeout.connect(self.update_clock)
        self.clock_timer.start(1000)

        self.fetch_timer = QtCore.QTimer(self)
        self.fetch_timer.timeout.connect(self.start_fetch)
        self.fetch_timer.start(60_000)  # fetch every 60s

        self.tray_icon = QSystemTray(self)

        self._update_clock_font()

        self.start_fetch()

    def update_clock(self) -> None:
        try:
            now = datetime.now(ZoneInfo(self.time_zone))
        except Exception:
            now = datetime.now(ZoneInfo(DEFAULT_TIMEZONE))
        self.time_label.setText(now.strftime('%H:%M:%S'))
        self.date_label.setText(now.strftime('%A, %B %d, %Y'))

    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:
        super().resizeEvent(event)
        self._update_clock_font()

    def _update_clock_font(self) -> None:
        available = self.left_frame.contentsRect()
        if available.width() <= 0 or available.height() <= 0:
            return

        font = self.time_label.font()
        font.setWeight(QtGui.QFont.Weight.Bold)

        margins = self.left_frame.layout().contentsMargins()
        title_height = self.time_title.sizeHint().height()
        date_height = self.date_label.sizeHint().height()
        spacing = self.left_frame.layout().spacing()

        target_width = max(available.width() - margins.left() - margins.right() - 20, 1)
        target_height = max(
            available.height()
            - margins.top()
            - margins.bottom()
            - title_height
            - date_height
            - (spacing * 2)
            - 24,
            1,
        )
        text = "88:88:88"

        low = 24
        high = 260
        best = low

        while low <= high:
            size = (low + high) // 2
            font.setPointSize(size)
            metrics = QtGui.QFontMetrics(font)
            rect = metrics.boundingRect(text)
            if rect.width() <= target_width and rect.height() <= target_height:
                best = size
                low = size + 1
            else:
                high = size - 1

        font.setPointSize(best)
        self.time_label.setFont(font)

    def start_fetch(self) -> None:
        self.status.setText("Fetching data...")
        self.thread = FetchThread()
        self.thread.data_ready.connect(self.on_data)
        self.thread.error.connect(self.on_error)
        self.thread.start()

    def on_data(self, payload: dict) -> None:
        location = payload["location"]
        weather = payload["weather"]
        current = weather.get("current", {})

        self.time_zone = location.get("timezone", DEFAULT_TIMEZONE)

        location_label = ", ".join(part for part in [location["city"], location["region"], location["country"]] if part)
        self.location_label.setText(f"{location_label}")

        temp = current.get("temperature_2m")
        apparent = current.get("apparent_temperature")
        ws = current.get("wind_speed_10m")
        hum = current.get("relative_humidity_2m")
        code_value = current.get("weather_code")
        code = int(code_value) if code_value is not None else 0
        label, emoji = weather_label(code)

        if temp is not None:
            self.weather_main.setText(f"{emoji}  {label}")
            self.now_label.setText(f"{temp:.1f} °C")
            if apparent is not None:
                self.feels_label.setText(f"Feels like: {apparent:.1f} °C")
            else:
                self.feels_label.setText("Feels like: —")
        else:
            self.weather_main.setText(f"{emoji}  {label}")
            self.now_label.setText("—")
            self.feels_label.setText("Feels like: —")

        if ws is not None and hum is not None:
            self.wind_label.setText(f"Wind: {ws:.0f} km/h  •  Humidity: {hum:.0f}%")
        elif ws is not None:
            self.wind_label.setText(f"Wind: {ws:.0f} km/h")
        elif hum is not None:
            self.wind_label.setText(f"Humidity: {hum:.0f}%")
        else:
            self.wind_label.setText("Wind: — | Humidity: —")

        self.status.setText("Last update: " + datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        self.update_clock()

    def on_error(self, message: str) -> None:
        self.status.setText("Error fetching data: " + message)

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        # minimize to tray instead of closing
        event.ignore()
        self.hide()
        self.tray_icon.show_message("Stardance Dashboard", "App minimized to tray.")


class QSystemTray(QtWidgets.QSystemTrayIcon):
    def __init__(self, parent: QtWidgets.QWidget | None = None):
        # create a simple icon pixmap
        pix = QtGui.QPixmap(64, 64)
        pix.fill(QtGui.QColor('#1E90FF'))
        icon = QtGui.QIcon(pix)
        super().__init__(icon, parent)
        self.parent = parent

        menu = QtWidgets.QMenu()
        restore_action = menu.addAction("Restore")
        restore_action.triggered.connect(self.restore)
        exit_action = menu.addAction("Exit")
        exit_action.triggered.connect(self.exit_app)
        self.setContextMenu(menu)
        self.activated.connect(self._activated)
        self.show()

    def _activated(self, reason):
        if reason == QtWidgets.QSystemTrayIcon.ActivationReason.Trigger:
            self.restore()

    def restore(self):
        if self.parent is not None:
            self.parent.show()
            self.parent.raise_()

    def exit_app(self):
        QtWidgets.QApplication.quit()

    def show_message(self, title: str, text: str) -> None:
        # some platforms need showMessage to display
        self.showMessage(title, text, QtGui.QIcon(), 2000)


def main() -> int:
    app = QtWidgets.QApplication(sys.argv)
    win = MainWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())

from http.server import HTTPServer, SimpleHTTPRequestHandler
import json
import os


STARRED_WIDGET_TO_KEY = {
    "weather-widget-star": "weather",
    "notifications-widget-star": "notifications",
    "date-time-widget-star": "dateTime",
    "countdown-widget-star": "countdown",
    "calendar-widget-star": "calendar",
    "stock-crypto-widget-star": "stockCrypto",
}


def _write_json_response(handler, status_code, payload):
    body = json.dumps(payload).encode()
    handler.send_response(status_code)
    handler.send_cors_headers()
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _validate_settings(data):
    widgets = data.get("widgets") or {}
    checked_widgets = [name for name, enabled in widgets.items() if enabled]

    if not checked_widgets:
        return "Please select at least one widget."

    starred_widget = data.get("starredWidget")
    if not starred_widget:
        return "Please star at least one widget."

    starred_widget_name = STARRED_WIDGET_TO_KEY.get(starred_widget)
    if starred_widget_name is None or not widgets.get(starred_widget_name, False):
        return "The starred widget must be one of the selected widgets."

    use_ip_location = bool(data.get("useIpLocation"))
    location = (data.get("location") or "").strip()

    if not use_ip_location and not location:
        return "Please enter a location or enable IP location."

    if not use_ip_location and not data.get("coordinates"):
        return "Location coordinates are missing."

    if use_ip_location and not data.get("coordinates"):
        return "IP location coordinates are missing."

    return None

class Handler(SimpleHTTPRequestHandler):

    def send_cors_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Private-Network", "true")

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_cors_headers()
        self.end_headers()

    def do_POST(self):
        if self.path == "/save":
            try:
                length = int(self.headers["Content-Length"])
                data = json.loads(self.rfile.read(length))
            except (TypeError, ValueError, json.JSONDecodeError):
                _write_json_response(self, 400, {"status": "error", "error": "Invalid settings payload."})
                return

            validation_error = _validate_settings(data)
            if validation_error:
                _write_json_response(self, 400, {"status": "error", "error": validation_error})
                return

            with open("settings.json", "w") as f:
                json.dump(data, f, indent=2)

            _write_json_response(self, 200, {"status": "ok"})

    def do_GET(self):
        if self.path == "/load":
            if os.path.exists("settings.json"):
                with open("settings.json", "r") as f:
                    content = f.read()
                self.send_response(200)
                self.send_cors_headers()
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(content.encode())
            else:
                self.send_response(404)
                self.send_cors_headers()
                self.end_headers()
        else:
            super().do_GET()

httpd = HTTPServer(("localhost", 8000), Handler)
print("Server läuft auf http://localhost:8000")
httpd.serve_forever()
from http.server import HTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import json
import os

from dotenv import load_dotenv
from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request as GoogleAuthRequest
from googleapiclient.discovery import build

load_dotenv()

GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET")
GOOGLE_REDIRECT_URI = os.environ.get("GOOGLE_REDIRECT_URI", "http://localhost:8000/auth/google/callback")
GOOGLE_SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]

SETTINGS_FILE = "settings.json"

# Temporary in-memory store mapping OAuth "state" -> PKCE code_verifier.
# This bridges the gap between /auth/google (which creates the Flow and its
# verifier) and /auth/google/callback (a separate request/Flow object that
# needs the same verifier to exchange the code for tokens).
_pending_oauth_states: dict[str, str] = {}


def _build_google_flow(code_verifier: str | None = None):
    client_config = {
        "web": {
            "client_id": GOOGLE_CLIENT_ID,
            "client_secret": GOOGLE_CLIENT_SECRET,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [GOOGLE_REDIRECT_URI],
        }
    }
    flow = Flow.from_client_config(
        client_config,
        scopes=GOOGLE_SCOPES,
        redirect_uri=GOOGLE_REDIRECT_URI,
    )
    if code_verifier:
        flow.code_verifier = code_verifier
    return flow


def _load_settings():
    if os.path.exists(SETTINGS_FILE):
        with open(SETTINGS_FILE, "r") as f:
            return json.load(f)
    return {}


def _save_settings(data):
    with open(SETTINGS_FILE, "w") as f:
        json.dump(data, f, indent=2)


def _store_google_tokens(credentials: Credentials):
    settings = _load_settings()
    settings["googleCalendar"] = {
        "connected": True,
        "token": credentials.token,
        "refreshToken": credentials.refresh_token,
        "tokenUri": credentials.token_uri,
        "clientId": credentials.client_id,
        "clientSecret": credentials.client_secret,
        "scopes": credentials.scopes,
        "expiry": credentials.expiry.isoformat() if credentials.expiry else None,
    }
    _save_settings(settings)


def _load_google_credentials():
    settings = _load_settings()
    token_data = settings.get("googleCalendar")
    if not token_data or not token_data.get("refreshToken"):
        return None

    credentials = Credentials(
        token=token_data.get("token"),
        refresh_token=token_data.get("refreshToken"),
        token_uri=token_data.get("tokenUri") or "https://oauth2.googleapis.com/token",
        client_id=token_data.get("clientId") or GOOGLE_CLIENT_ID,
        client_secret=token_data.get("clientSecret") or GOOGLE_CLIENT_SECRET,
        scopes=token_data.get("scopes") or GOOGLE_SCOPES,
    )

    if not credentials.valid:
        credentials.refresh(GoogleAuthRequest())
        _store_google_tokens(credentials)

    return credentials


def _disconnect_google():
    settings = _load_settings()
    settings.pop("googleCalendar", None)
    _save_settings(settings)


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

            # Preserve the googleCalendar token block; the settings form on the
            # frontend does not know about it and must not wipe it out on save.
            existing = _load_settings()
            if "googleCalendar" in existing and "googleCalendar" not in data:
                data["googleCalendar"] = existing["googleCalendar"]

            _save_settings(data)
            _write_json_response(self, 200, {"status": "ok"})

        elif self.path == "/calendar/disconnect":
            _disconnect_google()
            _write_json_response(self, 200, {"status": "ok"})

        else:
            _write_json_response(self, 404, {"status": "error", "error": "Unknown endpoint."})

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/load":
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

        elif path == "/auth/google":
            if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
                _write_json_response(self, 500, {"error": "Google OAuth is not configured on the server."})
                return
            flow = _build_google_flow()
            auth_url, state = flow.authorization_url(
                access_type="offline",
                include_granted_scopes="true",
                prompt="consent",
            )
            # Remember the PKCE verifier for this login attempt so the
            # callback request (a separate Flow object) can reuse it.
            _pending_oauth_states[state] = flow.code_verifier
            _write_json_response(self, 200, {"url": auth_url})

        elif path == "/auth/google/callback":
            params = parse_qs(parsed.query)
            code = params.get("code", [None])[0]
            error = params.get("error", [None])[0]
            state = params.get("state", [None])[0]

            if error:
                self._redirect_to_settings(f"google_error={error}")
                return
            if not code:
                self._redirect_to_settings("google_error=missing_code")
                return

            code_verifier = _pending_oauth_states.pop(state, None) if state else None

            try:
                flow = _build_google_flow(code_verifier=code_verifier)
                flow.fetch_token(code=code)
                _store_google_tokens(flow.credentials)
            except Exception as e:
                self._redirect_to_settings(f"google_error={e}")
                return

            self._redirect_to_settings("google_connected=1")

        elif path == "/calendar/events":
            credentials = _load_google_credentials()
            if credentials is None:
                _write_json_response(self, 401, {"error": "Google Calendar is not connected."})
                return
            try:
                service = build("calendar", "v3", credentials=credentials)
                result = service.events().list(
                    calendarId="primary",
                    timeMin=_now_iso(),
                    maxResults=10,
                    singleEvents=True,
                    orderBy="startTime",
                ).execute()
                _write_json_response(self, 200, {"events": result.get("items", [])})
            except Exception as e:
                _write_json_response(self, 500, {"error": str(e)})

        elif path == "/calendar/status":
            settings = _load_settings()
            connected = bool((settings.get("googleCalendar") or {}).get("connected"))
            _write_json_response(self, 200, {"connected": connected})

        else:
            super().do_GET()

    def _redirect_to_settings(self, query: str) -> None:
        self.send_response(302)
        self.send_cors_headers()
        self.send_header("Location", f"/settings.html?{query}")
        self.end_headers()


def _now_iso():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


httpd = HTTPServer(("localhost", 8000), Handler)
print("Server läuft auf http://localhost:8000")
httpd.serve_forever()
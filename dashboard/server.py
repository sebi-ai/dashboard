from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse, parse_qs, quote
import json
import os
import subprocess
import sys
import time
import requests
from dotenv import load_dotenv
from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request as GoogleAuthRequest
from googleapiclient.discovery import build

load_dotenv()

GOOGLE_CREDENTIALS_FILE = os.environ.get(
    "GOOGLE_CREDENTIALS_FILE",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "client_secret.json"),
)


def _normalize_client_id(client_id):
    """Tolerate pasting the client ID in URL form.

    Google client IDs look like `1234567890-abc.apps.googleusercontent.com`.
    If someone copies the value including a scheme (e.g. from a browser bar)
    the OAuth exchange fails with `401 invalid_client` — strip the scheme and
    any trailing/path slashes so it matches what Google expects.
    """
    if not client_id:
        return client_id
    client_id = client_id.strip()
    if "://" in client_id:
        client_id = client_id.split("://", 1)[1]
    client_id = client_id.split("/", 1)[0].strip("/")
    return client_id


def _load_google_client_config():
    """Build the Google OAuth client config from .env vars or client_secret.json.

    Environment variables (documented in the README) take priority:
      GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_REDIRECT_URI
    """
    client_id = _normalize_client_id(os.environ.get("GOOGLE_CLIENT_ID") or None)
    client_secret = os.environ.get("GOOGLE_CLIENT_SECRET") or None

    if client_id and client_secret:
        redirect_uri = os.environ.get(
            "GOOGLE_REDIRECT_URI", "http://localhost:8000/auth/google/callback"
        )
        return {
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uris": [redirect_uri],
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }

    if os.path.exists(GOOGLE_CREDENTIALS_FILE):
        with open(GOOGLE_CREDENTIALS_FILE, "r") as f:
            data = json.load(f)
        return data.get("web") or data.get("installed")

    return None


_google_client_config = _load_google_client_config()

GOOGLE_CLIENT_ID = _google_client_config.get("client_id") if _google_client_config else None
GOOGLE_CLIENT_SECRET = _google_client_config.get("client_secret") if _google_client_config else None

_DEFAULT_REDIRECT_URI = "http://localhost:8000/auth/google/callback"
_configured_redirect_uris = (
    [u for u in (_google_client_config.get("redirect_uris") or []) if isinstance(u, str)]
    if _google_client_config
    else []
)
# Pick the redirect URI Google will accept. A client_secret.json can list several
# URIs, and Google rejects the exchange with `redirect_uri_mismatch` unless the
# one used here is registered for this client. Priority:
#   1. an explicit GOOGLE_REDIRECT_URI env override (documented as taking priority)
#   2. a configured URI that matches this app's callback
#   3. the first configured URI (the file's own ordering)
#   4. the localhost default
GOOGLE_REDIRECT_URI = (
    os.environ.get("GOOGLE_REDIRECT_URI")
    or next((u for u in _configured_redirect_uris if u == _DEFAULT_REDIRECT_URI), None)
    or next((u for u in _configured_redirect_uris if u.endswith("/auth/google/callback")), None)
    or (_configured_redirect_uris[0] if _configured_redirect_uris else None)
    or _DEFAULT_REDIRECT_URI
)
GOOGLE_SCOPES = [
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/gmail.readonly",
]

ALPHA_VANTAGE_API_KEY = os.environ.get("ALPHA_VANTAGE_API_KEY")
CMC_API_KEY = os.environ.get("CMC_API_KEY")

SETTINGS_FILE = "settings.json"

_pending_oauth_states = {}

_cmc_map_cache = {"data": None, "fetched_at": 0}
_CMC_MAP_CACHE_SECONDS = 60 * 60

_dashboard_proc = None


def _get_cmc_map():
    now = time.time()
    if _cmc_map_cache["data"] is not None and (now - _cmc_map_cache["fetched_at"]) < _CMC_MAP_CACHE_SECONDS:
        return _cmc_map_cache["data"]
    response = requests.get(
        "https://pro-api.coinmarketcap.com/v1/cryptocurrency/map",
        headers={"X-CMC_PRO_API_KEY": CMC_API_KEY},
        params={"listing_status": "active", "limit": 5000},
        timeout=10,
    )
    response.raise_for_status()
    data = response.json().get("data", [])
    _cmc_map_cache["data"] = data
    _cmc_map_cache["fetched_at"] = now
    return data


def _dedupe_results(results):
    """Remove duplicate symbols while keeping the first occurrence."""
    seen = set()
    unique = []
    for result in results:
        symbol = (result.get("symbol") or "").strip()
        key = (result.get("type"), symbol.upper())
        if not symbol or key in seen:
            continue
        seen.add(key)
        unique.append(result)
    return unique[:8]


def _search_stocks(keywords):
    """Search stocks. Yahoo Finance works without an API key; Alpha Vantage is
    used as an additional source when ALPHA_VANTAGE_API_KEY is configured."""
    results = []

    try:
        response = requests.get(
            "https://query1.finance.yahoo.com/v1/finance/search",
            params={
                "q": keywords,
                "quotesCount": 8,
                "newsCount": 0,
                "listsCount": 0,
            },
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=10,
        )
        response.raise_for_status()
        for quote in response.json().get("quotes", []):
            quote_type = (quote.get("quoteType") or "").upper()
            if quote_type not in ("EQUITY", "ETF", "INDEX"):
                continue
            results.append({
                "type": "stock",
                "symbol": quote.get("symbol"),
                "name": quote.get("shortname") or quote.get("longname") or quote.get("symbol"),
                "region": quote.get("exchDisp") or quote.get("exchange"),
            })
    except Exception as e:
        print("Yahoo Finance search failed:", e)

    if ALPHA_VANTAGE_API_KEY:
        try:
            response = requests.get(
                "https://www.alphavantage.co/query",
                params={
                    "function": "SYMBOL_SEARCH",
                    "keywords": keywords,
                    "apikey": ALPHA_VANTAGE_API_KEY,
                },
                timeout=10,
            )
            response.raise_for_status()
            for m in response.json().get("bestMatches", []):
                results.append({
                    "type": "stock",
                    "symbol": m.get("1. symbol"),
                    "name": m.get("2. name"),
                    "region": m.get("4. region"),
                })
        except Exception as e:
            print("Alpha Vantage search failed:", e)

    return _dedupe_results(results)


def _search_crypto(keywords):
    """Search crypto. CoinGecko works without an API key; CoinMarketCap is used
    as an additional source when CMC_API_KEY is configured."""
    results = []
    keywords_lower = keywords.lower()

    try:
        response = requests.get(
            "https://api.coingecko.com/api/v3/search",
            params={"query": keywords},
            timeout=10,
        )
        response.raise_for_status()
        for coin in response.json().get("coins", []):
            results.append({
                "type": "crypto",
                "symbol": coin.get("symbol"),
                "name": coin.get("name"),
                "id": coin.get("id"),
            })
            if len(results) >= 8:
                break
    except Exception as e:
        print("CoinGecko search failed:", e)

    if CMC_API_KEY:
        try:
            coins = _get_cmc_map()
            for coin in coins:
                name = coin.get("name", "")
                symbol = coin.get("symbol", "")
                if keywords_lower in name.lower() or keywords_lower in symbol.lower():
                    results.append({
                        "type": "crypto",
                        "symbol": symbol,
                        "name": name,
                        "id": coin.get("id"),
                    })
        except Exception as e:
            print("CoinMarketCap search failed:", e)

    return _dedupe_results(results)


_coingecko_id_cache = {}


def _coingecko_id_for(symbol, name):
    """Resolve a CoinGecko coin id from a symbol/name (cached)."""
    key = (name or symbol or "").strip().lower()
    if not key:
        return None
    if key in _coingecko_id_cache:
        return _coingecko_id_cache[key]

    symbol_lower = (symbol or "").lower()
    coin_id = symbol_lower
    try:
        response = requests.get(
            "https://api.coingecko.com/api/v3/search",
            params={"query": name or symbol},
            timeout=10,
        )
        response.raise_for_status()
        coins = response.json().get("coins", [])
        for coin in coins:
            if coin.get("symbol", "").lower() == symbol_lower:
                coin_id = coin["id"]
                break
        else:
            if coins:
                coin_id = coins[0]["id"]
    except Exception:
        pass

    _coingecko_id_cache[key] = coin_id
    return coin_id


def _fetch_crypto_price(symbol, name):
    coin_id = _coingecko_id_for(symbol, name)
    response = requests.get(
        "https://api.coingecko.com/api/v3/simple/price",
        params={
            "ids": coin_id,
            "vs_currencies": "usd",
            "include_24hr_change": "true",
            "include_market_cap": "true",
        },
        timeout=10,
    )
    response.raise_for_status()
    data = response.json()
    coin = data.get(coin_id) or (list(data.values())[0] if data else {})
    if not coin:
        return {"error": "Cryptocurrency not found on CoinGecko."}
    return {
        "price": coin.get("usd"),
        "change": coin.get("usd_24h_change"),
        "marketCap": coin.get("usd_market_cap"),
    }


def _fetch_stock_price_yahoo(symbol):
    """Keyless stock quote via the Yahoo Finance chart endpoint."""
    response = requests.get(
        f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}",
        params={"range": "2d", "interval": "1d"},
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=10,
    )
    response.raise_for_status()
    result = (response.json().get("chart", {}).get("result") or [None])[0]
    if not result:
        return None
    meta = result.get("meta", {})
    closes = (result.get("indicators", {}).get("quote", [{}])[0] or {}).get("close") or []
    price = meta.get("regularMarketPrice")
    if price is None and closes:
        price = closes[-1]
    if price is None:
        return None
    change = None
    if len(closes) >= 2 and closes[-2]:
        change = (closes[-1] / closes[-2] - 1) * 100
    return {"price": price, "change": change, "marketCap": None}


def _fetch_stock_price(symbol):
    """Stock quote: Alpha Vantage when a key is configured, otherwise (or on
    failure) the keyless Yahoo Finance chart endpoint."""
    if ALPHA_VANTAGE_API_KEY:
        try:
            response = requests.get(
                "https://www.alphavantage.co/query",
                params={
                    "function": "GLOBAL_QUOTE",
                    "symbol": symbol,
                    "apikey": ALPHA_VANTAGE_API_KEY,
                },
                timeout=10,
            )
            response.raise_for_status()
            quote = response.json().get("Global Quote") or {}
            price = quote.get("05. price")
            if price is not None:
                try:
                    price_value = float(price)
                except (TypeError, ValueError):
                    price_value = None
                try:
                    change_value = float(
                        str(quote.get("10. change percent", "0%")).replace("%", "").strip()
                    )
                except (TypeError, ValueError):
                    change_value = 0.0
                return {"price": price_value, "change": change_value, "marketCap": None}
        except Exception as e:
            print("Alpha Vantage quote failed, falling back to Yahoo:", e)

    yahoo = _fetch_stock_price_yahoo(symbol)
    if yahoo:
        return yahoo
    if ALPHA_VANTAGE_API_KEY:
        return {"error": "No quote returned for this symbol."}
    return {"error": "Could not fetch a quote for this symbol. Try again later."}


def _build_google_flow(code_verifier=None, redirect_uri=None):
    if not _google_client_config:
        raise RuntimeError(f"Google credentials file '{GOOGLE_CREDENTIALS_FILE}' not found or invalid.")
    client_config = {"web": _google_client_config}
    flow = Flow.from_client_config(
        client_config,
        scopes=GOOGLE_SCOPES,
        redirect_uri=redirect_uri or GOOGLE_REDIRECT_URI,
    )
    if code_verifier:
        flow.code_verifier = code_verifier
    return flow


def _request_redirect_uri(handler):
    """Redirect URI Google should send the browser back to for this request.

    GOOGLE_REDIRECT_URI can point at a production domain even while the server
    is used from localhost, which makes Google send the OAuth callback to a
    place this process never sees. Derive the URI from the request's own Host
    header so the callback always lands back on this server.
    """
    host = (handler.headers.get("Host") or "").strip()
    if not host:
        return GOOGLE_REDIRECT_URI

    # If the configured URI already targets this exact host, use it verbatim so
    # a production HTTPS redirect keeps working behind a reverse proxy.
    configured_host = (
        GOOGLE_REDIRECT_URI.split("://", 1)[-1].split("/", 1)[0]
        if GOOGLE_REDIRECT_URI
        else ""
    )
    if configured_host == host:
        return GOOGLE_REDIRECT_URI

    # The built-in server speaks plain HTTP on the loopback interface.
    if host.startswith(("localhost", "127.0.0.1")):
        return f"http://{host}/auth/google/callback"

    # Otherwise derive from the forwarded protocol so the same server also
    # works behind a public HTTPS reverse proxy.
    forwarded_proto = (handler.headers.get("X-Forwarded-Proto") or "http").split(",")[0].strip().lower()
    scheme = forwarded_proto if forwarded_proto in ("http", "https") else "http"
    return f"{scheme}://{host}/auth/google/callback"


def _google_oauth_error_hint(raw_error):
    """Map raw Google OAuth errors to something a user can act on."""
    text = (raw_error or "").strip()
    lowered = text.lower()
    hints = {
        "deleted_client": (
            "The Google OAuth client was deleted. Create a new OAuth 2.0 Client ID in "
            "Google Cloud Console and update GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET in .env."
        ),
        "invalid_client": (
            "The Google OAuth client is invalid. Check GOOGLE_CLIENT_ID and "
            "GOOGLE_CLIENT_SECRET in .env."
        ),
        "redirect_uri_mismatch": (
            "The callback URL is not registered for this client. Add it as an "
            "authorized redirect URI in Google Cloud Console."
        ),
        "access_denied": "You declined the Google permission request.",
        "unauthorized_client": (
            "This client is not allowed to use the requested scopes. Enable the "
            "Google Calendar API and Gmail API in Google Cloud Console."
        ),
        "invalid_grant": "Google rejected the login (invalid_grant). Disconnect and connect again.",
    }
    for key, hint in hints.items():
        if key in lowered:
            return hint
    return text or "Unknown Google OAuth error."


def _load_settings():
    if os.path.exists(SETTINGS_FILE):
        with open(SETTINGS_FILE, "r") as f:
            return json.load(f)
    return {}


def _save_settings(data):
    with open(SETTINGS_FILE, "w") as f:
        json.dump(data, f, indent=2)


def _store_google_tokens(credentials):
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


SENSITIVE_PATH_PARTS = (".env", "client_secret", "settings.json")


def _is_sensitive_path(path: str) -> bool:
    """Block static-file requests that would expose secrets or source code.

    SimpleHTTPRequestHandler serves everything it can reach, so without this
    guard anyone on localhost could download settings.json (contains the Google
    refresh token), client_secret.json, the .py sources, etc.
    """
    p = path.lower()
    if any(part in p for part in SENSITIVE_PATH_PARTS):
        return True
    if p.endswith((".json", ".py", ".log")):
        return True
    # Any hidden file/directory segment (e.g. /.well-known is fine, /__pycache__ is not)
    if any(seg.startswith(".") and seg not in (".", "..") for seg in path.split("/")):
        return True
    return False


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

    theme_mode = data.get("themeMode")
    if theme_mode not in ("preset", "custom"):
        return "Please select a theme."
    if theme_mode == "preset" and not (data.get("theme") or "").strip():
        return "Please select a preset theme."
    if theme_mode == "custom" and not (data.get("customColor") or "").strip():
        return "Please choose a custom color."

    use_ip_location = bool(data.get("useIpLocation"))
    location = (data.get("location") or "").strip()
    if not use_ip_location and not location:
        return "Please enter a location or enable IP location."
    if not use_ip_location and not data.get("coordinates"):
        return "Location coordinates are missing."
    if use_ip_location and not data.get("coordinates"):
        return "IP location coordinates are missing."
    return None


def _launch_dashboard():
    global _dashboard_proc

    # Replace any running instance so the dashboard always runs the latest
    # code (a stale process would otherwise keep showing old widgets/corners).
    if _dashboard_proc is not None and _dashboard_proc.poll() is None:
        try:
            _dashboard_proc.terminate()
            _dashboard_proc.wait(timeout=5)
        except Exception:
            try:
                _dashboard_proc.kill()
            except Exception:
                pass
        _dashboard_proc = None

    script_dir = os.path.dirname(os.path.abspath(__file__))
    dashboard_path = os.path.join(script_dir, "dashboard.py")

    if not os.path.exists(dashboard_path):
        return False, f"dashboard.py not found in: {script_dir}"

    try:
        kwargs = {}
        if sys.platform == "win32":
            kwargs["creationflags"] = subprocess.CREATE_NEW_CONSOLE
        else:
            kwargs["start_new_session"] = True

        _dashboard_proc = subprocess.Popen(
            [sys.executable, dashboard_path],
            cwd=script_dir,
            **kwargs,
        )
        return True, f"Dashboard started (PID {_dashboard_proc.pid})"
    except Exception as exc:
        return False, str(exc)


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
        if self.path == "/launch":
            ok, msg = _launch_dashboard()
            if ok:
                _write_json_response(self, 200, {"status": "ok", "message": msg})
            else:
                _write_json_response(self, 500, {"status": "error", "error": msg})
            return

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

            existing = _load_settings()
            if "googleCalendar" in existing:
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
                body = content.encode()
                self.send_response(200)
                self.send_cors_headers()
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            else:
                _write_json_response(self, 404, {"error": "No settings saved yet."})

        elif path == "/auth/google":
            if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
                _write_json_response(self, 500, {"error": "Google OAuth is not configured on the server."})
                return
            redirect_uri = _request_redirect_uri(self)
            flow = _build_google_flow(redirect_uri=redirect_uri)
            auth_url, state = flow.authorization_url(
                access_type="offline",
                include_granted_scopes="true",
                prompt="consent",
            )
            _pending_oauth_states[state] = {
                "code_verifier": flow.code_verifier,
                "redirect_uri": redirect_uri,
            }
            _write_json_response(self, 200, {"url": auth_url})

        elif path == "/auth/google/callback":
            params = parse_qs(parsed.query)
            code = params.get("code", [None])[0]
            error = params.get("error", [None])[0]
            state = params.get("state", [None])[0]
            if error:
                self._redirect_to_settings(f"google_error={quote(_google_oauth_error_hint(error))}")
                return
            if not code:
                self._redirect_to_settings("google_error=missing_code")
                return
            pending = _pending_oauth_states.pop(state, None) if state else None
            code_verifier = pending.get("code_verifier") if pending else None
            redirect_uri = pending.get("redirect_uri") if pending else _request_redirect_uri(self)
            try:
                flow = _build_google_flow(code_verifier=code_verifier, redirect_uri=redirect_uri)
                flow.fetch_token(code=code)
                _store_google_tokens(flow.credentials)
            except Exception as e:
                self._redirect_to_settings(f"google_error={quote(_google_oauth_error_hint(str(e)))}")
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

        elif path == "/finance/search":
            params = parse_qs(parsed.query)
            query = (params.get("q", [""])[0] or "").strip()
            if len(query) < 1:
                _write_json_response(self, 200, {"results": []})
                return
            try:
                results = _search_stocks(query) + _search_crypto(query)
            except Exception as e:
                print("Finance search failed:", e)
                results = []
            _write_json_response(self, 200, {"results": results})

        elif path == "/finance/price":
            params = parse_qs(parsed.query)
            finance_type = (params.get("type", [""])[0] or "").lower()
            symbol = (params.get("symbol", [""])[0] or "").strip()
            name = (params.get("name", [""])[0] or "").strip()

            if finance_type == "stock":
                if not symbol:
                    _write_json_response(self, 400, {"error": "Missing symbol."})
                    return
                try:
                    _write_json_response(self, 200, _fetch_stock_price(symbol))
                except Exception as e:
                    _write_json_response(self, 500, {"error": str(e)})
            elif finance_type == "crypto":
                if not symbol and not name:
                    _write_json_response(self, 400, {"error": "Missing symbol or name."})
                    return
                try:
                    _write_json_response(self, 200, _fetch_crypto_price(symbol, name))
                except Exception as e:
                    _write_json_response(self, 500, {"error": str(e)})
            else:
                _write_json_response(self, 400, {"error": "Invalid type. Use 'stock' or 'crypto'."})

        elif path == "/notifications/messages":
            credentials = _load_google_credentials()
            if credentials is None:
                _write_json_response(self, 401, {"error": "Google Mail is not connected."})
                return
            try:
                service = build("gmail", "v1", credentials=credentials)
                listing = service.users().messages().list(
                    userId="me",
                    labelIds=["INBOX"],
                    maxResults=10,
                ).execute()
                message_refs = listing.get("messages", [])
                messages = []
                for ref in message_refs:
                    full = service.users().messages().get(
                        userId="me",
                        id=ref["id"],
                        format="metadata",
                        metadataHeaders=["From", "Subject", "Date"],
                    ).execute()
                    headers = {h["name"]: h["value"] for h in full.get("payload", {}).get("headers", [])}
                    messages.append({
                        "id": full.get("id"),
                        "from": headers.get("From", "(unknown sender)"),
                        "subject": headers.get("Subject", "(no subject)"),
                        "date": headers.get("Date", ""),
                        "snippet": full.get("snippet", ""),
                        "unread": "UNREAD" in full.get("labelIds", []),
                    })
                _write_json_response(self, 200, {"messages": messages})
            except Exception as e:
                error_text = str(e)
                if "insufficient" in error_text.lower() or "403" in error_text:
                    _write_json_response(self, 403, {
                        "error": "Missing Gmail permission. Please disconnect and reconnect Google to grant access to your inbox."
                    })
                else:
                    _write_json_response(self, 500, {"error": error_text})

        else:
            if _is_sensitive_path(path):
                self.send_response(403)
                self.send_cors_headers()
                self.end_headers()
                return
            super().do_GET()

    def do_HEAD(self):
        # Same protection as do_GET: HEAD must not leak file metadata for secrets.
        parsed = urlparse(self.path)
        if _is_sensitive_path(parsed.path):
            self.send_response(403)
            self.send_cors_headers()
            self.end_headers()
            return
        super().do_HEAD()

    def _redirect_to_settings(self, query):
        self.send_response(302)
        self.send_cors_headers()
        self.send_header("Location", f"/settings.html?{query}")
        self.end_headers()


def _now_iso():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


# Threading server: each request runs in its own thread, so one slow/stuck
# connection can never freeze the whole site.
httpd = ThreadingHTTPServer(("localhost", 8000), Handler)
print("Server runs on http://localhost:8000")
httpd.serve_forever()

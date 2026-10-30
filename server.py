from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse, parse_qs, quote
from datetime import datetime, timezone
import json
import os
import glob
import re
import signal
import socket
import subprocess
import sys
import threading
import time
import requests
from dotenv import load_dotenv
from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request as GoogleAuthRequest
from google.auth.exceptions import RefreshError
from googleapiclient.discovery import build

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

import glob

# Google's Cloud Console downloads the OAuth client as
# `client_secret_<client-id>.json`, so the server auto-discovers any such file
# instead of requiring an exact `client_secret.json` rename. An explicit
# GOOGLE_CREDENTIALS_FILE env var always wins.
def _resolve_google_credentials_file():
    env_path = os.environ.get("GOOGLE_CREDENTIALS_FILE")
    if env_path:
        return env_path
    base = os.path.dirname(os.path.abspath(__file__))
    exact = os.path.join(base, "client_secret.json")
    if os.path.exists(exact):
        return exact
    candidates = glob.glob(os.path.join(base, "client_secret*.json"))
    if candidates:
        candidates.sort(key=lambda p: os.path.getmtime(p), reverse=True)
        return candidates[0]
    return exact


GOOGLE_CREDENTIALS_FILE = _resolve_google_credentials_file()


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

SETTINGS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "settings.json")

_pending_oauth_states = {}

_cmc_map_cache = {"data": None, "fetched_at": 0}
_CMC_MAP_CACHE_SECONDS = 60 * 60

_dashboard_proc = None
_streamlit_proc = None

# The Streamlit web app runs on the loopback interface only and is NOT exposed
# to the network. The browser reaches it exclusively through this server's own
# port: every path under /app/... is reverse-proxied to the local Streamlit
# process (including its WebSocket), so a single port/domain serves everything.
STREAMLIT_PORT = 8501
STREAMLIT_UPSTREAM = f"http://127.0.0.1:{STREAMLIT_PORT}"
STREAMLIT_BASE_PATH = "/app"
DASHBOARD_URL_PATH = "/app/"


def _streamlit_healthy(timeout=2.0):
    """True when the (baseUrlPath-aware) Streamlit health endpoint answers."""
    try:
        r = requests.get(
            f"{STREAMLIT_UPSTREAM}{STREAMLIT_BASE_PATH}/_stcore/health",
            timeout=timeout,
        )
        return r.status_code == 200
    except Exception:
        return False


def _port_in_use(port, timeout=0.5):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(timeout)
        return s.connect_ex(("127.0.0.1", port)) == 0


def _kill_stale_streamlit_listeners():
    """Kill unknown processes listening on the Streamlit port.

    Streamlit is started detached, so an instance from a previous server.py run
    (or an old version serving without the /app base path) can still occupy the
    port. Without this, a freshly spawned Streamlit would crash-loop on the
    busy port while the stale one keeps answering on the wrong paths.
    """
    pids = set()
    try:
        if os.name == "nt":
            out = subprocess.run(
                ["netstat", "-ano", "-p", "TCP"],
                capture_output=True, text=True, timeout=10,
                # netstat emits OEM-encoded text on Windows (e.g. CP850 on
                # German systems); strict UTF-8 decoding would crash here.
                errors="replace",
            ).stdout
            for line in out.splitlines():
                parts = line.split()
                # Proto  Local            Foreign   State        PID
                # A listener always has 0.0.0.0:0 as its foreign address —
                # language-independent (Windows localizes "LISTENING", e.g.
                # "ABHÖREN" on German systems).
                if len(parts) >= 5 and parts[1].endswith(f":{STREAMLIT_PORT}") \
                        and parts[2] in ("0.0.0.0:0", "[::]:0"):
                    pids.add(parts[4])
        else:
            # lsof is not installed on every minimal server; ss (iproute2) is
            # present on virtually all modern distros — try both.
            for cmd in (
                ["lsof", "-t", "-i", f":{STREAMLIT_PORT}"],
                ["ss", "-ltnp", f"sport = :{STREAMLIT_PORT}"],
            ):
                try:
                    out = subprocess.run(
                        cmd, capture_output=True, text=True, timeout=10,
                        errors="replace",
                    ).stdout or ""
                except FileNotFoundError:
                    continue
                except Exception as e:
                    print(f"Could not query processes on port {STREAMLIT_PORT}: {e}")
                    continue
                if cmd[0] == "lsof":
                    pids.update(line.strip() for line in out.splitlines() if line.strip())
                else:
                    # ss:  LISTEN 0 128 *:8501  *:*  users:(("streamlit",pid=1234,fd=18))
                    pids.update(re.findall(r"pid=(\d+)", out))
                if pids:
                    break
    except Exception as e:
        print(f"Could not look up processes on port {STREAMLIT_PORT}: {e}")
        return False

    killed = False
    for pid_str in pids:
        try:
            pid = int(pid_str)
        except ValueError:
            continue
        if pid == os.getpid():
            continue
        try:
            if os.name == "nt":
                subprocess.run(
                    ["taskkill", "/F", "/PID", str(pid)],
                    capture_output=True, timeout=10,
                )
            else:
                os.kill(pid, signal.SIGKILL)
            killed = True
            print(f"Killed stale process {pid} on port {STREAMLIT_PORT}")
        except Exception as e:
            print(f"Could not kill stale process {pid}: {e}")
    return killed


def _launch_streamlit():
    global _streamlit_proc

    # A streamlit instance that is already serving (e.g. started by a previous
    # server.py run — it is detached and survives the parent) already has the
    # port. Spawning another one would crash-loop on the busy port while the
    # still-working old instance keeps answering, so probe first.
    if _streamlit_healthy():
        return True, "Streamlit dashboard already running"

    # Replace any running instance so the dashboard always runs the latest code
    if _streamlit_proc is not None and _streamlit_proc.poll() is None:
        try:
            _streamlit_proc.terminate()
            _streamlit_proc.wait(timeout=5)
        except Exception:
            try:
                _streamlit_proc.kill()
            except Exception:
                pass
        _streamlit_proc = None

    if _port_in_use(STREAMLIT_PORT):
        # Something else holds the port (leftover detached Streamlit from an
        # older version, without the /app base path). Remove it, then retry.
        _kill_stale_streamlit_listeners()
        if _port_in_use(STREAMLIT_PORT):
            return False, (
                f"Port {STREAMLIT_PORT} is used by another process that could "
                "not be stopped. Close it and try again."
            )
        time.sleep(0.5)

    script_dir = os.path.dirname(os.path.abspath(__file__))
    streamlit_script = os.path.join(script_dir, "dashboard.py")

    if not os.path.exists(streamlit_script):
        return False, f"dashboard.py not found in: {script_dir}"

    try:
        # Use start_new_session on all platforms so the subprocess runs
        # detached from the parent (no console window on Windows, no
        # terminal attachment on macOS/Linux). Avoid CREATE_NEW_CONSOLE
        # because that can trigger an elevation prompt on Windows.
        kwargs = {"start_new_session": True}

        # Bound to 127.0.0.1 only: the app is reachable exclusively through
        # this server's reverse proxy (/app/...), never directly from outside.
        # baseUrlPath makes Streamlit serve everything under /app so the proxy
        # can forward paths verbatim. fileWatcherType=none speeds up boot; the
        # dashboard picks up settings changes on every rerun anyway.
        _streamlit_proc = subprocess.Popen(
            [sys.executable, "-m", "streamlit", "run", streamlit_script,
             "--server.address=127.0.0.1",
             f"--server.port={STREAMLIT_PORT}",
             f"--server.baseUrlPath={STREAMLIT_BASE_PATH.lstrip('/')}",
             "--server.headless=true",
             "--server.fileWatcherType=none",
             "--server.enableCORS=false",
             "--server.enableXsrfProtection=false",
             "--browser.gatherUsageStats=false"],
            cwd=script_dir,
            **kwargs,
        )
        return True, f"Streamlit dashboard started (PID {_streamlit_proc.pid})"
    except Exception as exc:
        return False, str(exc)


def _wait_for_streamlit(timeout=30.0):
    """Block until the Streamlit health endpoint answers (or timeout)."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if _streamlit_healthy(timeout=1.0):
            return True
        time.sleep(0.25)
    return False


def _ensure_streamlit_ready(wait=30.0):
    """Make sure Streamlit is up AND ready to serve, waiting if needed.

    Called by /webapp so the browser only gets "ok" once the dashboard can
    actually render — the client then just opens /app/ with no polling.
    """
    if _streamlit_healthy():
        return True, "Streamlit dashboard already running"
    ok, msg = _launch_streamlit()
    if not ok:
        return False, msg
    if _wait_for_streamlit(wait):
        return True, msg
    return False, (
        f"{msg}, but it did not become ready within {int(wait)}s. "
        "Check the server console for Streamlit errors."
    )


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
        for q in response.json().get("quotes", []):
            quote_type = (q.get("quoteType") or "").upper()
            if quote_type not in ("EQUITY", "ETF", "INDEX"):
                continue
            results.append({
                "type": "stock",
                "symbol": q.get("symbol"),
                "name": q.get("shortname") or q.get("longname") or q.get("symbol"),
                "region": q.get("exchDisp") or q.get("exchange"),
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

    # Retry up to 2 times to tolerate CoinGecko's free-tier rate limit (HTTP 429).
    for attempt in range(3):
        try:
            response = requests.get(
                "https://api.coingecko.com/api/v3/search",
                params={"query": keywords},
                timeout=10,
            )
            if response.status_code == 429:
                if attempt < 2:
                    time.sleep(1 + attempt)
                    continue
                print("CoinGecko search rate-limited:", response.status_code)
                break
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
            break
        except Exception as e:
            print("CoinGecko search failed:", e)
            break

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

    try:
        yahoo = _fetch_stock_price_yahoo(symbol)
    except Exception as e:
        # Unknown/invalid symbols make Yahoo respond with 404/400; surface a
        # clean error message instead of the raw "404 Client Error ..." text.
        print("Yahoo Finance quote failed:", e)
        yahoo = None
    if yahoo:
        return yahoo
    if ALPHA_VANTAGE_API_KEY:
        return {"error": "No quote returned for this symbol."}
    return {"error": "Could not fetch a quote for this symbol. Try again later."}


# Chart ranges for /finance/history: Yahoo range/interval for stocks (keyless
# chart API) and CoinGecko day counts for crypto (market_chart).
_FINANCE_HISTORY_RANGES = {
    "1D": {"yahoo": ("1d", "5m"), "days": 1},
    "1W": {"yahoo": ("5d", "15m"), "days": 7},
    "1M": {"yahoo": ("1mo", "60m"), "days": 30},
    "3M": {"yahoo": ("3mo", "1d"), "days": 90},
}


def _fetch_stock_history(symbol, yahoo_range, yahoo_interval):
    """Historical closes for a stock via the keyless Yahoo chart endpoint.

    Returns ``[[ms_timestamp, close], ...]`` usable by the widget's chart,
    skipping null closes (Yahoo pads the series with nulls for halted days).
    """
    response = requests.get(
        f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}",
        params={"range": yahoo_range, "interval": yahoo_interval},
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=10,
    )
    response.raise_for_status()
    result = (response.json().get("chart", {}).get("result") or [None])[0]
    if not result:
        return []
    timestamps = result.get("timestamp") or []
    closes = (result.get("indicators", {}).get("quote", [{}])[0] or {}).get("close") or []
    points = []
    for ts, close in zip(timestamps, closes):
        if close is None:
            continue
        points.append([ts * 1000, close])
    return points


def _fetch_crypto_history(coin_id, days):
    """Historical closes for a crypto via CoinGecko's market_chart endpoint."""
    response = requests.get(
        f"https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart",
        params={"vs_currency": "usd", "days": str(int(days))},
        timeout=15,
    )
    response.raise_for_status()
    # prices already come as [[ms, close], ...]
    return [
        [p[0], p[1]]
        for p in (response.json().get("prices") or [])
        if len(p) >= 2 and p[1] is not None
    ]


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
    # Loopback variants (localhost / 127.0.0.1 / [::1]) all normalize to
    # `localhost`: Google only accepts exact redirect URIs, and this client
    # registers the localhost form — deriving e.g. http://127.0.0.1:8000/...
    # would make Google reject the login with `redirect_uri_mismatch`.
    hostname = (
        host[: host.find("]") + 1] if host.startswith("[") else host.split(":", 1)[0]
    )
    if hostname in ("localhost", "127.0.0.1", "[::1]", "::1"):
        loopback_host = host if hostname == "localhost" else host.replace(hostname, "localhost", 1)
        return f"http://{loopback_host}/auth/google/callback"

    # Otherwise derive from the forwarded protocol so the same server also
    # works behind a public HTTPS reverse proxy.
    forwarded_proto = (handler.headers.get("X-Forwarded-Proto") or "http").split(",")[0].strip().lower()
    scheme = forwarded_proto if forwarded_proto in ("http", "https") else "http"
    return f"{scheme}://{host}/auth/google/callback"


def _prune_oauth_states():
    """Drop pending OAuth state entries older than 10 minutes.

    Each /auth/google click adds an entry; it is only popped when the OAuth
    round-trip completes. Users who click 'Connect' and never finish (closed
    tab, declined earlier) would otherwise accumulate entries forever.
    """
    cutoff = time.time() - 600
    stale = [s for s, entry in _pending_oauth_states.items() if entry.get("ts", 0) < cutoff]
    for s in stale:
        _pending_oauth_states.pop(s, None)


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
    # Internal (library-level) errors must not leak raw tracebacks to the
    # settings page — show an actionable line instead.
    internal_markers = (
        "typeerror", "valueerror", "attributeerror", "keyerror",
        "traceback (most recent call last)", "oauthlib.",
        "got multiple values", "unexpected keyword",
    )
    if any(marker in lowered for marker in internal_markers):
        return (
            "Google sign-in failed internally. Try connecting again; if it keeps "
            "failing, restart server.py and check its console output."
        )
    return text or "Unknown Google OAuth error."


def _load_settings():
    if os.path.exists(SETTINGS_FILE):
        with open(SETTINGS_FILE, "r") as f:
            return json.load(f)
    return {}


def _save_settings(data):
    """Write settings atomically (temp file + rename).

    The server is threaded: /save, token refreshes and /load can overlap, and
    both dashboard processes re-read the file concurrently (hot-reload). Writing
    in place could let a reader see a half-written file; os.replace is atomic
    on Windows (NTFS) so readers only ever see the old or the complete file.
    """
    tmp = SETTINGS_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, SETTINGS_FILE)


def _token_expiry_ms(credentials):
    """Credential expiry as epoch milliseconds (google-auth returns naive UTC)."""
    if not credentials.expiry:
        return None
    exp = credentials.expiry
    if exp.tzinfo is None:
        exp = exp.replace(tzinfo=timezone.utc)
    return int(exp.timestamp() * 1000)


def _credentials_from_bearer(access_token):
    """Per-request Google credentials taken from the calling browser.

    The server NEVER stores Google logins. Every data request must carry its
    own access token (Authorization: Bearer ...), so a visitor can only ever
    read the account that was connected in their own browser.
    """
    return Credentials(token=access_token, scopes=GOOGLE_SCOPES)


def _is_google_auth_error(exc):
    """True when Google rejected the request as unauthenticated/unauthorized."""
    # google-auth raises RefreshError when a request comes back 401 and the
    # server-side credentials carry no refresh token — which is ALWAYS the
    # case here, because the refresh token deliberately lives in the calling
    # browser. Surface it as 401 so that browser refreshes its own token
    # (via /auth/refresh) and retries.
    if isinstance(exc, RefreshError):
        return True
    resp = getattr(exc, "resp", None)
    status = getattr(resp, "status", None)
    if status == 401:
        return True
    text = str(exc).lower()
    return "401" in text or "invalid credentials" in text or "unauthorized" in text


def _send_google_token_page(handler, credentials):
    """Hand the freshly exchanged OAuth tokens to the connecting browser.

    The browser stores them in its own localStorage — the server keeps NO
    copy — and is then redirected back to the settings page. The OAuth
    callback runs in the same tab that started the connect, so the tokens
    land in exactly the browser that initiated the login.
    """
    if not credentials.refresh_token:
        # The browser-side code (script.js getGoogleTokens) only accepts a
        # login that carries a refresh token — without one the access token
        # dies within the hour and cannot be renewed, so the login would
        # report "not connected" right after connecting. Google skips the
        # refresh token only when offline access was granted earlier WITHOUT
        # re-consent; the connect request always sends prompt=consent, so
        # this is a safety net that fails loudly instead of silently.
        handler._redirect_to_settings(
            "google_error=" + quote(
                "Google did not issue a refresh token. Disconnect and connect "
                "again; if this keeps happening, remove this app's access in "
                "your Google account settings and connect again."
            )
        )
        return
    payload = {
        "access_token": credentials.token,
        "refresh_token": credentials.refresh_token,
        "expiryMs": _token_expiry_ms(credentials),
        "scopes": list(credentials.scopes or []),
    }
    # Embed as JSON; escape "</" so a crafted value can never close the tag.
    token_json = json.dumps(payload).replace("</", "<\\/")
    page = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="referrer" content="no-referrer">
<title>Google connected</title>
</head>
<body>
<p>Google account connected. Storing the login in this browser&hellip;</p>
<noscript>JavaScript is required to store the login in this browser.</noscript>
<script>
try {{
  // IMPORTANT: the tokens must be stored as a JSON STRING. Passing the
  // object itself to localStorage.setItem would store "[object Object]" —
  // garbage that JSON.parse rejects, making every page report
  // "Google is not connected in this browser" right after a login.
  var tokens = {token_json};
  localStorage.setItem("dashboardGoogleTokens", JSON.stringify(tokens));
  location.replace("/settings.html?google_connected=1");
}} catch (e) {{
  document.body.textContent = "Could not store the login in this browser: " + e;
  location.replace("/settings.html?google_error=" +
      encodeURIComponent("Could not store the login in this browser: " + e));
}}
</script>
</body>
</html>"""
    body = page.encode("utf-8")
    handler.send_response(200)
    handler.send_header("Content-Type", "text/html; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Cache-Control", "no-store")
    handler.send_header("Referrer-Policy", "no-referrer")
    handler.end_headers()
    handler.wfile.write(body)


SENSITIVE_PATH_PARTS = (".env", "client_secret", "settings.json", "__pycache__")


def _is_sensitive_path(path: str) -> bool:
    """Block static-file requests that would expose secrets or source code.

    SimpleHTTPRequestHandler serves everything it can reach, so without this
    guard anyone on localhost could download settings.json (contains the Google
    refresh token), client_secret.json, the .py sources, etc. Compiled .pyc
    files effectively contain the same source, so they are blocked too.
    """
    p = path.lower()
    if any(part in p for part in SENSITIVE_PATH_PARTS):
        return True
    if p.endswith((".json", ".py", ".pyc", ".log")):
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
    if not isinstance(widgets, dict):
        # A manual/API caller could send any JSON type for `widgets`; treat it
        # as empty instead of crashing on .items() (would surface as HTTP 500).
        widgets = {}
    checked_widgets = [name for name, enabled in widgets.items() if enabled]
    if not checked_widgets:
        return "Please select at least one widget."

    theme_mode = data.get("themeMode")
    if theme_mode not in ("preset", "custom"):
        return "Please select a theme."
    if theme_mode == "preset" and not str(data.get("theme") or "").strip():
        return "Please select a preset theme."
    if theme_mode == "custom" and not str(data.get("customColor") or "").strip():
        return "Please choose a custom color."

    use_ip_location = bool(data.get("useIpLocation"))
    location = str(data.get("location") or "").strip()
    coordinates = data.get("coordinates")
    if not isinstance(coordinates, dict):
        coordinates = None
    if not use_ip_location and not location:
        return "Please enter a location or enable IP location."
    if not use_ip_location and not coordinates:
        return "Location coordinates are missing."
    if use_ip_location and not coordinates:
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
        # Use start_new_session on all platforms so the subprocess runs
        # detached from the parent (no console window on Windows, no
        # terminal attachment on macOS/Linux). Avoid CREATE_NEW_CONSOLE
        # because that can trigger an elevation prompt on Windows.
        kwargs = {"start_new_session": True}

        _dashboard_proc = subprocess.Popen(
            [sys.executable, dashboard_path],
            cwd=script_dir,
            **kwargs,
        )
        return True, f"Dashboard started (PID {_dashboard_proc.pid})"
    except Exception as exc:
        return False, str(exc)


# Cross-origin browser reads are only allowed for this app's own pages: the
# website (served from :8000) and the Streamlit web dashboard (:8501). Every
# other origin gets no CORS headers, so a random website the user is browsing
# cannot read responses like /load (which contains the Google refresh token)
# via fetch() from their browser. Same-origin fetches never need CORS.
CORS_ALLOWED_ORIGINS = (
    "http://localhost:8000", "http://127.0.0.1:8000",
    "http://localhost:8501", "http://127.0.0.1:8501",
)

# Headers that must not be copied 1:1 when reverse-proxying to Streamlit:
# hop-by-hop headers plus the ones this side re-computes (Host, lengths,
# encoding — upstream is always asked for identity encoding so bodies can be
# inspected/injected without decompressing).
_HOP_BY_HOP_HEADERS = {
    "host", "connection", "keep-alive", "proxy-authenticate",
    "proxy-authorization", "te", "trailer", "trailers", "transfer-encoding",
    "upgrade", "content-length", "content-encoding", "accept-encoding",
}

_RESPONSE_HEADERS_TO_SKIP = {
    "connection", "keep-alive", "transfer-encoding", "content-encoding",
    "content-length", "server", "date",
}

# Browsers cannot force real fullscreen from a parent page, so the dashboard
# page itself asks for fullscreen on the first user interaction (click or key).
# A no-op catch: without a gesture the request is simply denied.
_FULLSCREEN_SNIPPET = (
    "<script>(function(){var done=false;var go=function(){"
    "if(done)return;done=true;"
    "var el=document.documentElement;"
    "if(el.requestFullscreen){el.requestFullscreen().catch(function(){});}};"
    "document.addEventListener('click',go,{once:true});"
    "document.addEventListener('keydown',go,{once:true});})();</script>"
)

_STARTING_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta http-equiv="refresh" content="1">
<title>Dashboard</title>
<style>
  html,body{{margin:0;height:100%;font-family:'Segoe UI',system-ui,sans-serif;
    background:#0d0d1a;color:#e0e0ff;display:flex;align-items:center;justify-content:center;}}
  .box{{text-align:center;}}
  .spin{{width:42px;height:42px;margin:0 auto 18px;border-radius:50%;
    border:3px solid #2a2a50;border-top-color:#00d4ff;animation:s 0.9s linear infinite;}}
  @keyframes s{{to{{transform:rotate(360deg);}}}}
  p{{margin:4px 0;letter-spacing:1px;}}
  .hint{{color:#6666aa;font-size:13px;}}
</style>
</head>
<body>
<div class="box">
  <div class="spin"></div>
  <p>Dashboard is starting&hellip;</p>
  <p class="hint">This page continues automatically once the dashboard is ready.</p>
</div>
{fullscreen}
</body>
</html>"""


def _inject_fullscreen_script(html: bytes) -> bytes:
    """Insert the fullscreen-on-first-interaction snippet into an HTML page."""
    text = html.decode("utf-8", errors="replace")
    snippet = _FULLSCREEN_SNIPPET
    if "</body>" in text:
        text = text.replace("</body>", snippet + "</body>", 1)
    else:
        text += snippet
    return text.encode("utf-8")


_upstream_session_instance = None


def _upstream_session():
    """Shared requests.Session so proxy requests reuse pooled connections."""
    global _upstream_session_instance
    if _upstream_session_instance is None:
        _upstream_session_instance = requests.Session()
    return _upstream_session_instance


class Handler(SimpleHTTPRequestHandler):
    # Declare UTF-8 explicitly: without a charset in Content-Type some HTTP
    # clients (curl, requests, older browsers without meta-sniffing) render
    # em-dashes and emoji on the pages as mojibake.
    extensions_map = {
        **SimpleHTTPRequestHandler.extensions_map,
        ".html": "text/html; charset=utf-8",
        ".js": "text/javascript; charset=utf-8",
        ".css": "text/css; charset=utf-8",
        ".json": "application/json; charset=utf-8",
        ".md": "text/markdown; charset=utf-8",
    }

    def __init__(self, *args, **kwargs):
        # Serve the website from the script's directory, not the process CWD.
        # Without this, `python C:\...\server.py` started from any other
        # folder (VS Code task, autostart, scheduler) serves a 404 site while
        # the API endpoints still respond — very confusing to debug.
        super().__init__(*args, directory=os.path.dirname(os.path.abspath(__file__)), **kwargs)

    def send_cors_headers(self):
        origin = (self.headers.get("Origin") or "").strip()
        if origin in CORS_ALLOWED_ORIGINS:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.send_header("Access-Control-Allow-Private-Network", "true")
        # Deliberately no wildcard: a missing CORS header makes cross-origin
        # responses unreadable in browsers, which is exactly what we want for
        # all other origins. Non-browser clients are unaffected.

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_cors_headers()
        self.end_headers()

    # --- Reverse proxy to the local Streamlit app (/app/...) ----------------

    def _is_streamlit_path(self, path):
        return path == STREAMLIT_BASE_PATH or path.startswith(STREAMLIT_BASE_PATH + "/")

    def _handle_streamlit(self):
        if (self.headers.get("Upgrade") or "").strip().lower() == "websocket":
            self._proxy_streamlit_websocket()
        else:
            self._proxy_streamlit_http()

    def _serve_starting_page(self):
        """Shown when Streamlit is still booting (e.g. /app/ opened directly).

        Auto-refreshes every second, so it continues into the dashboard on its
        own — no clicking required.
        """
        body = _STARTING_PAGE.format(fullscreen=_FULLSCREEN_SNIPPET).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _proxy_streamlit_http(self):
        parsed = urlparse(self.path)
        is_doc = self.command in ("GET", "HEAD") and parsed.path in (
            STREAMLIT_BASE_PATH, STREAMLIT_BASE_PATH + "/",
        )

        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else None
        fwd = {
            k: v for k, v in self.headers.items()
            if k.lower() not in _HOP_BY_HOP_HEADERS
        }
        # Identity encoding: lets us inject into the HTML document without
        # having to decompress anything.
        fwd["Accept-Encoding"] = "identity"

        try:
            resp = _upstream_session().request(
                self.command, STREAMLIT_UPSTREAM + self.path,
                headers=fwd, data=body, stream=True,
                allow_redirects=False, timeout=(3, 120),
            )
        except requests.exceptions.RequestException:
            if is_doc:
                self._serve_starting_page()
            else:
                _write_json_response(self, 502, {
                    "error": "Dashboard backend is not ready yet. Try again."
                })
            return

        try:
            self.send_response(resp.status_code)
            for k, v in resp.headers.items():
                low = k.lower()
                if low == "location":
                    # Never leak the internal upstream address (e.g. the 307
                    # /app -> /app/ redirect): point the client back at this
                    # server with a relative URL instead.
                    self.send_header(k, v.replace(STREAMLIT_UPSTREAM, ""))
                    continue
                if low not in _RESPONSE_HEADERS_TO_SKIP:
                    self.send_header(k, v)
            self.close_connection = True
            self.send_header("Connection", "close")

            payload = None
            content_type = resp.headers.get("Content-Type") or ""
            if (
                is_doc and self.command == "GET"
                and "text/html" in content_type
            ):
                # The app shell is the one page the user sees — give it the
                # fullscreen-on-first-interaction behavior.
                payload = _inject_fullscreen_script(resp.content)
                self.send_header("Content-Length", str(len(payload)))
            else:
                upstream_len = resp.headers.get("Content-Length")
                if upstream_len:
                    self.send_header("Content-Length", upstream_len)
            self.end_headers()

            if self.command == "HEAD":
                return
            if payload is not None:
                self.wfile.write(payload)
            else:
                try:
                    for chunk in resp.iter_content(65536):
                        if chunk:
                            self.wfile.write(chunk)
                except (requests.exceptions.RequestException, ConnectionError):
                    # Upstream died mid-transfer; the client sees the truncated
                    # (close-delimited) response. Nothing more we can do here.
                    pass
        except (BrokenPipeError, ConnectionResetError):
            pass  # client went away (e.g. navigated/refreshed)
        finally:
            resp.close()

    def _proxy_streamlit_websocket(self):
        """Tunnel the Streamlit WebSocket through this server.

        Reads the handshake, replays it verbatim to the local Streamlit (paths
        match 1:1 thanks to baseUrlPath), forwards the 101 response and then
        splices the two sockets together without interpreting frames.
        """
        try:
            backend = socket.create_connection(
                ("127.0.0.1", STREAMLIT_PORT), timeout=5
            )
        except OSError:
            self.send_response(502)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return

        try:
            # No timeout for the long-lived tunneled connection (the 5s above
            # would otherwise drop an idle dashboard session).
            backend.settimeout(None)

            raw = self.raw_requestline + b"".join(
                f"{k}: {v}\r\n".encode("latin-1")
                for k, v in self.headers.items()
            ) + b"\r\n"
            backend.sendall(raw)

            buf = b""
            while b"\r\n\r\n" not in buf and len(buf) < 65536:
                chunk = backend.recv(4096)
                if not chunk:
                    raise ConnectionError(
                        "backend closed during WebSocket handshake"
                    )
                buf += chunk

            head, sep, rest = buf.partition(b"\r\n\r\n")
            status = head.split(b"\r\n", 1)[0].split()
            code = int(status[1]) if len(status) >= 2 and status[1].isdigit() else 0
            self.close_connection = True

            self.wfile.write(head + sep)
            if code != 101:
                if rest:
                    self.wfile.write(rest)
                return

            self.wfile.flush()
            if rest:
                self.connection.sendall(rest)

            def pump(reader, dst):
                """Copy one direction until EOF, then half-close the target."""
                try:
                    while True:
                        data = reader(65536)
                        if not data:
                            break
                        dst.sendall(data)
                except OSError:
                    pass
                finally:
                    try:
                        dst.shutdown(socket.SHUT_WR)
                    except OSError:
                        pass

            up = threading.Thread(
                target=pump,
                args=(lambda n: self.rfile.read1(n), backend),
                daemon=True,
            )
            down = threading.Thread(
                target=pump,
                args=(lambda n: backend.recv(n), self.connection),
                daemon=True,
            )
            up.start()
            down.start()
            # This request thread stays alive for the whole WebSocket session —
            # that is what keeps the tunnel open while the server framework
            # would otherwise close the socket after do_* returns.
            up.join()
            down.join(timeout=10)
        except OSError:
            pass
        finally:
            try:
                backend.close()
            except OSError:
                pass

    def do_POST(self):
        if self._is_streamlit_path(urlparse(self.path).path):
            self._handle_streamlit()
            return

        if self.path == "/webapp":
            # Wait until Streamlit can actually serve before answering, so the
            # browser can open /app/ immediately — no client-side polling.
            ok, msg = _ensure_streamlit_ready()
            if ok:
                _write_json_response(self, 200, {
                    "status": "ok", "message": msg, "url": DASHBOARD_URL_PATH,
                })
            else:
                _write_json_response(self, 500, {"status": "error", "error": msg})
            return

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

            # Google logins live only in each browser's localStorage — never
            # persist them, no matter what a client sends.
            data.pop("googleCalendar", None)
            _save_settings(data)
            _write_json_response(self, 200, {"status": "ok"})
            return

        if self.path == "/settings/render":
            # Render the dashboard for a browser-provided settings payload.
            # Budget-style browsers each keep their settings in their own
            # localStorage; this endpoint only turns the POSTed payload into
            # the dashboard HTML — it NEVER writes settings.json. Visitors
            # therefore see (and change) only their own settings.
            try:
                length = int(self.headers.get("Content-Length") or 0)
                data = json.loads(self.rfile.read(length) or b"{}")
            except (TypeError, ValueError, json.JSONDecodeError):
                data = {}
            if not isinstance(data, dict) or not data:
                data = _load_settings()
            try:
                import dashboard
                _css, html = dashboard.render_dashboard_html(data)
            except Exception as e:
                print("Dashboard render failed:", e)
                _write_json_response(self, 500, {"error": str(e)[:200]})
                return
            body = (_css + html).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if self.path == "/auth/refresh":
            # Exchange a browser-provided refresh token for a fresh access
            # token. Stateless: nothing is stored, the client keeps the token.
            try:
                length = int(self.headers.get("Content-Length") or 0)
                data = json.loads(self.rfile.read(length) or b"{}")
            except (TypeError, ValueError, json.JSONDecodeError):
                data = {}
            refresh_token = (data.get("refresh_token") or "").strip()
            if not refresh_token:
                _write_json_response(self, 400, {"error": "Missing refresh_token."})
                return
            if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
                _write_json_response(self, 500, {"error": "Google OAuth is not configured on the server."})
                return
            credentials = Credentials(
                token=None,
                refresh_token=refresh_token,
                token_uri="https://oauth2.googleapis.com/token",
                client_id=GOOGLE_CLIENT_ID,
                client_secret=GOOGLE_CLIENT_SECRET,
                scopes=GOOGLE_SCOPES,
            )
            try:
                credentials.refresh(GoogleAuthRequest())
            except Exception as e:
                print(f"Google token refresh failed: {e}")
                # 401 tells the browser this login is dead and must be
                # re-established (its own localStorage entry only).
                _write_json_response(self, 401, {"error": "Google login expired. Please connect again."})
                return
            _write_json_response(self, 200, {
                "access_token": credentials.token,
                "refresh_token": credentials.refresh_token or refresh_token,
                "expiryMs": _token_expiry_ms(credentials),
            })
            return

        else:
            _write_json_response(self, 404, {"status": "error", "error": "Unknown endpoint."})

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if self._is_streamlit_path(path):
            self._handle_streamlit()
            return

        if path == "/load":
            if os.path.exists(SETTINGS_FILE):
                with open(SETTINGS_FILE, "r") as f:
                    try:
                        data = json.load(f)
                    except (json.JSONDecodeError, ValueError):
                        data = {}
                # settings.json stores the Google credentials (incl. the
                # refresh token). No browser ever needs them — this endpoint
                # is called by every visitor's settings page, and they used
                # to receive the full credential set. Serve everything
                # EXCEPT those secrets; the server keeps using the stored
                # values, and /save preserves the block via _load_settings().
                data.pop("googleCalendar", None)
                # Widgets are per-browser: a fresh visitor must never inherit
                # the owner's enabled set (which used to tick every checkbox).
                # Every browser starts with none and chooses its own — the
                # rest of the seed (location/theme) still applies.
                data.pop("widgets", None)
                body = json.dumps(data).encode()
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
            _prune_oauth_states()
            _pending_oauth_states[state] = {
                "code_verifier": flow.code_verifier,
                "redirect_uri": redirect_uri,
                "ts": time.time(),
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
                # Do NOT pass redirect_uri here: google_auth_oauthlib >= 0.8
                # forwards kwargs to requests_oauthlib, which already injects the
                # flow's own redirect_uri. A second value raises
                # "got multiple values for keyword argument 'redirect_uri'".
                flow.fetch_token(code=code)
            except Exception as e:
                self._redirect_to_settings(f"google_error={quote(_google_oauth_error_hint(str(e)))}")
                return
            # Success: give the tokens to the connecting browser only. Nothing
            # is written to disk — each browser owns its login from here on.
            _send_google_token_page(self, flow.credentials)

        elif path == "/calendar/events":
            access_token = self._bearer_token()
            if not access_token:
                _write_json_response(self, 401, {"error": "Google Calendar is not connected in this browser."})
                return
            try:
                service = build("calendar", "v3", credentials=_credentials_from_bearer(access_token))
                result = service.events().list(
                    calendarId="primary",
                    timeMin=_now_iso(),
                    maxResults=10,
                    singleEvents=True,
                    orderBy="startTime",
                ).execute()
                _write_json_response(self, 200, {"events": result.get("items", [])})
            except Exception as e:
                if _is_google_auth_error(e):
                    _write_json_response(self, 401, {"error": "Google login expired. Please connect again."})
                else:
                    _write_json_response(self, 500, {"error": str(e)})

        elif path == "/calendar/status":
            # Kept for compatibility; connection state lives in each browser,
            # so the server can only report "not connected".
            _write_json_response(self, 200, {"connected": False})

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

        elif path == "/finance/history":
            # Historical closes for the stocks widget's chart.
            params = parse_qs(parsed.query)
            finance_type = (params.get("type", [""])[0] or "").lower()
            symbol = (params.get("symbol", [""])[0] or "").strip()
            name = (params.get("name", [""])[0] or "").strip()
            range_key = (params.get("range", ["1D"])[0] or "1D").upper()
            if range_key not in _FINANCE_HISTORY_RANGES:
                range_key = "1D"

            if finance_type == "stock":
                if not symbol:
                    _write_json_response(self, 400, {"error": "Missing symbol."})
                    return
                yahoo_range, yahoo_interval = _FINANCE_HISTORY_RANGES[range_key]["yahoo"]
                try:
                    _write_json_response(self, 200, {
                        "points": _fetch_stock_history(symbol, yahoo_range, yahoo_interval),
                        "range": range_key,
                    })
                except Exception as e:
                    _write_json_response(self, 502, {"error": str(e)[:120]})
            elif finance_type == "crypto":
                if not symbol and not name:
                    _write_json_response(self, 400, {"error": "Missing symbol or name."})
                    return
                try:
                    days = _FINANCE_HISTORY_RANGES[range_key]["days"]
                    _write_json_response(self, 200, {
                        "points": _fetch_crypto_history(_coingecko_id_for(symbol, name), days),
                        "range": range_key,
                    })
                except Exception as e:
                    _write_json_response(self, 502, {"error": str(e)[:120]})
            else:
                _write_json_response(self, 400, {"error": "Unknown type."})

        elif path == "/notifications/messages":
            access_token = self._bearer_token()
            if not access_token:
                _write_json_response(self, 401, {"error": "Google Mail is not connected in this browser."})
                return
            try:
                service = build("gmail", "v1", credentials=_credentials_from_bearer(access_token))
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
                lowered = error_text.lower()
                if _is_google_auth_error(e):
                    _write_json_response(self, 401, {
                        "error": "Google login expired. Please connect again."
                    })
                elif (
                    "precondition check failed" in lowered
                    or "failedprecondition" in lowered
                ):
                    # Google returned FAILED_PRECONDITION: this happens when the
                    # authorized Google identity has no Gmail mailbox (e.g. an
                    # @freenet.de or other non-Google address registered as a
                    # Google account). Calendar still works for those accounts,
                    # Gmail API never does. Surfacing the reason beats a bare 500.
                    _write_json_response(self, 400, {
                        "error": (
                            "No Gmail mailbox on this Google account.\n"
                            "The Messages widget needs an account with Gmail "
                            "(@gmail.com or a Workspace mailbox). Please connect "
                            "such an account in Settings, or disable this widget."
                        )
                    })
                elif "insufficient" in lowered or "403" in error_text:
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
        if self._is_streamlit_path(parsed.path):
            self._handle_streamlit()
            return
        if _is_sensitive_path(parsed.path):
            self.send_response(403)
            self.send_cors_headers()
            self.end_headers()
            return
        super().do_HEAD()

    def _bearer_token(self):
        """Access token the calling browser sent with this request (or None)."""
        auth = (self.headers.get("Authorization") or "").strip()
        if auth.lower().startswith("bearer "):
            return auth[7:].strip() or None
        return None

    def _redirect_to_settings(self, query):
        self.send_response(302)
        self.send_cors_headers()
        self.send_header("Location", f"/settings.html?{query}")
        self.end_headers()


def _now_iso():
    from datetime import timezone
    return datetime.now(timezone.utc).isoformat()


# HOST=0.0.0.0 makes the site reachable from outside (required when hosting on
# a server behind a domain); set HOST=127.0.0.1 to restrict it to this machine.
# PORT can be changed without touching the code (then also update the Google
# OAuth redirect URI). The Streamlit subprocess inherits PORT so its server
# callbacks (weather, prices, calendar) hit this server on the right port.
HOST = os.environ.get("HOST", "0.0.0.0")
PORT = int(os.environ.get("PORT", "8000"))
os.environ["PORT"] = str(PORT)

# Threading server: each request runs in its own thread, so one slow/stuck
# connection can never freeze the whole site.
if __name__ == "__main__":
    # Pre-warm the Streamlit app right at startup so "Start Dashboard" later
    # opens instantly instead of waiting for a cold boot on first click.
    ok, msg = _launch_streamlit()
    print(f"[streamlit] {msg}")

    httpd = ThreadingHTTPServer((HOST, PORT), Handler)
    display_host = "localhost" if HOST in ("0.0.0.0", "", "::") else HOST
    print(f"Website + API : http://{display_host}:{PORT}")
    print(f"Web dashboard : http://{display_host}:{PORT}{DASHBOARD_URL_PATH}"
          f"  ('Start Dashboard' opens this in a new tab; everything runs on"
          f" this single port — Streamlit itself stays on 127.0.0.1 only)")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.")

# Dashboard

A simple and easy to understand Python dashboard - built with HTML, CSS, Python and JS. Backed by server.py.

---

# Features

- **Widgets**: Enable as many widgets as you want and arrange them freely in Settings → Align Widgets — drag a widget by its body to move it anywhere, hover its corner and pull to resize it to any size (no snapping). The other widgets automatically move out of the way, fill any empty space, and no widget can grow so big that it hides the rest. Every widget keeps a minimum size so its content always fits, and text scales with the card so nothing ever gets clipped
- **Adaptive widgets**: every widget scales its content to its card, so big cards show big text instead of empty space
- **Themes**: Pick from 7 preset color themes or choose your own color and create your own theme
- **Location**: If you don't want your IP to be tracked or you are using a VPN you can also choose a Location instead of letting the dashboard track your IP
- **Settings**: All settings are saved in a .json file, so the Python code is able to read it

---

# Project Structure

dashboard/
├── index.html          # Main page (navigation, settings, basically everything you want to change)
├── script.js           # Frontend logic (settings, save/load, alerts)
├── styles.css          # Styling and everything
├── server.py           # Local Python HTTP server with the save/load API
├── dashboard.py        # Python Tkinter dashboard application
└── settings.json       # Auto-generated while saving your settings, so don't edit manually

---

# Starting your dashboard

1. **Clone or download** this repo
2. **Start the Python server** in the project folder:
   ```bash
   python3 server.py
   ```
3. **Open your browser** and navigate to:
   http://localhost:8000
4. **Configure your dashboard**
   - Press Settings in the menu
   - Edit the settings as you want
   - Save your settings
5. **Press Open Dashboard -> Start Dashboard** to start your dashboard

---

# API Endpoints

The Python server exposes these endpoints used by the frontend:

Method | Path | Description
-------|---------------------------|----------------------------------
POST | /save | Save settings in settings.json
GET | /load | Returns the current settings.json
GET | /auth/google | Returns the Google OAuth login URL
GET | /auth/google/callback | Google redirects here after login; stores tokens in settings.json
GET | /launch | Launch the dashboard.py application
GET | /calendar/status | Returns whether Google Calendar is connected
GET | /calendar/events | Returns the next 10 upcoming events from the connected calendar
POST | /calendar/disconnect | Removes the stored Google Calendar tokens
GET | /finance/search | Searches stocks (Alpha Vantage) and crypto (CoinMarketCap) by keyword
GET | /finance/price | Returns the current price/24h change for a stock (Alpha Vantage) or crypto (CoinGecko)
GET | /notifications/messages | Returns the latest Gmail inbox messages (uses the same Google login as Calendar)

All other GET requests are served as static files (HTML, CSS, JS).

---

# Stock / Crypto Setup

To use the Stock/Crypto widget:

1. Start the server, open **Settings**, and check the **Stock/Crypto Prices** widget checkbox.
2. Type a company or coin name, pick a suggestion, and press **Save**.

**No API keys are required for basic use anymore** — the search falls back to keyless sources (Yahoo Finance for stocks, CoinGecko for crypto), and prices use Yahoo Finance / CoinGecko as well.

For richer/extra results you can optionally add keys to your `.env` file:
   ```
   ALPHA_VANTAGE_API_KEY=your-alpha-vantage-key
   CMC_API_KEY=your-coinmarketcap-key
   ```
   Alpha Vantage is then used for stock search/quotes and CoinMarketCap for crypto search; if either key is missing or fails, the keyless fallback kicks in automatically.

The selected stock or crypto (type, symbol, name) is stored locally in `settings.json` under the `stockCryptoSelection` key. Prices are shown by the Python dashboard via the `/finance/price` endpoint.

Note: Alpha Vantage's free tier is limited to 25 requests/day. CoinMarketCap's cryptocurrency list is cached on the server for an hour to avoid hitting rate limits while you type.

---

# Google Calendar Setup

To use the Calendar widget with your real Google Calendar:

1. Go to the [Google Cloud Console](https://console.cloud.google.com/), create a project (or use an existing one) and enable the **Google Calendar API** (and the **Gmail API** if you want the Notifications widget).
2. Under **APIs & Services → Credentials**, create an **OAuth 2.0 Client ID** of type "Web application".
3. Add `http://localhost:8000/auth/google/callback` as an authorized redirect URI.
4. Create a `.env` file in the project folder (it's already in `.gitignore`, so it won't be committed) with:
   ```
   GOOGLE_CLIENT_ID=your-client-id
   GOOGLE_CLIENT_SECRET=your-client-secret
   GOOGLE_REDIRECT_URI=http://localhost:8000/auth/google/callback
   ```
   Alternatively, you can drop a downloaded `client_secret.json` (from Google Cloud Console) into the project folder — the server picks it up automatically.
5. Start the server, open **Settings**, press **Connect Google Calendar** (or **Connect Google Mail** — both connect the same Google account and cover Calendar + Gmail).

The access and refresh tokens are stored locally in `settings.json` under the `googleCalendar` key, so both the website and the Python dashboard (`dashboard.py`) use the same connection. Nothing is sent anywhere except directly to Google's own servers.

**Important:** never commit your real `.env` file or share your client secret. If it's ever exposed accidentally, regenerate it in the Google Cloud Console.

## Troubleshooting Google login

Calendar and Gmail share a **single** OAuth client and a single consent screen (the server requests both the `calendar.readonly` and `gmail.readonly` scopes at once), so fixing the client fixes both widgets.

- **`401 deleted_client` ("The OAuth client was deleted")** — the client ID in your `.env` no longer exists in Google Cloud Console. It cannot be recovered from the app side. Create a **new** OAuth 2.0 Client ID (type "Web application") under **APIs & Services → Credentials**, copy its new client ID and secret into `.env`, and register `http://localhost:8000/auth/google/callback` as an authorized redirect URI.
- **`redirect_uri_mismatch`** — the callback URL used by the app is not registered for that client. The server derives the callback URL from the address you actually open (e.g. `http://localhost:8000/auth/google/callback`), so add exactly that URL under the client's **Authorized redirect URIs**.
- **`access_denied`** — you pressed cancel on the consent screen. Just try again and allow access.
- **`403` / "Missing Gmail permission"** — an older connection was authorized without the Gmail scope. Use **Disconnect** and connect again; the fresh consent screen asks for both Calendar and Gmail.

If you change the port, update the redirect URI accordingly (e.g. `http://localhost:8001/auth/google/callback`) both in Google Cloud Console and in `GOOGLE_REDIRECT_URI`.

---

# Notes

- The server currently must be running locally for settings to save and load properly
- Settings are only stored locally, nothing is sent to any external server
- **Hot reload**: while the Python dashboard (`dashboard.py`) is running, it watches `settings.json` and rebuilds itself automatically ~1 second after you press **Save Settings** on the website — no need to restart the dashboard manually

---

# Contact

You have questions, feedback or inspiration? Feel free to contact me at
 tx.9394.tx@outlook.de

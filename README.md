# Dashboard

A simple and easy to understand python dashboard - built with HTML, CSS, Phython and JS. Backed by server.py.

---

# Features
 
- **Widgets** Choose up to three widget and a big one to be displayed on your dashboard
- **Themes** Pick from 7 preset color themes or choose your own color and create an own theme
- **Location** If you don't want your IP to be tracked or you a using a VPN you can also choose a Location instead of letting the dashboard track your IP
- **Settings** All settings are saved in a .json file, so the python code is able to read it

---

# Project Structure

dashboard/
├── index.html      # Main page (navigation, settings, basically everything, want to change this)
├── script.js       # Frontend logic (settings, save/load, alerts)
├── styles.css      # Styling and everything
├── server.py       # Local Python HTTP server with the save/load API
└── settings.json   # Auto-generated while saving your settings, so don't edit manually

---

# Starting your dashboard

1. **Clone or download** this repo
2. **Start the python server** in the project folder: 
    python3 server.py
3. **Open your browser** and navigate to:
    http://localhost:8000
4. **Configure your dashboard** 
    - Press Settings in the menu
    - Edit the settings as you want
    - Save your settings
5. **Press open Dashboard -> Start dashboard** to start your dashboard

---

# API Endpoints
The python server exposes these endpoints used by the frontend:

Method  |   Path                    |   Description
--------|---------------------------|----------------------------------
POST    | /save                     | Save settings in settings.json
GET     | /load                     | Returns the current settings.json
GET     | /auth/google              | Returns the Google OAuth login URL
GET     | /auth/google/callback     | Google redirects here after login; stores tokens in settings.json
GET     | /calendar/status          | Returns whether Google Calendar is connected
GET     | /calendar/events          | Returns the next 10 upcoming events from the connected calendar
POST    | /calendar/disconnect      | Removes the stored Google Calendar tokens
GET     | /finance/search           | Searches stocks (Alpha Vantage) and crypto (CoinMarketCap) by keyword

All other GET requests are served as static files (HTML, CSS, JS).

---

# Stock / Crypto Setup

To use the Stock/Crypto widget:

1. Get a free API key from [Alpha Vantage](https://www.alphavantage.co/support/#api-key) (for stocks).
2. Get a free API key from [CoinMarketCap](https://coinmarketcap.com/api/) (for crypto).
3. Add both keys to your `.env` file:
   ```
   ALPHA_VANTAGE_API_KEY=your-alpha-vantage-key
   CMC_API_KEY=your-coinmarketcap-key
   ```
4. Start the server, open **Settings**, and check the **Stock/Crypto Prices** widget checkbox.
5. Type a company or coin name, pick a suggestion, and press **Save**.

The selected stock or crypto (type, symbol, name) is stored locally in `settings.json` under the `stockCryptoSelection` key.

Note: Alpha Vantage's free tier is limited to 25 requests/day. CoinMarketCap's cryptocurrency list is cached on the server for an hour to avoid hitting rate limits while you type.

---

# Google Calendar Setup

To use the Calendar widget with your real Google Calendar:

1. Go to the [Google Cloud Console](https://console.cloud.google.com/), create a project (or use an existing one) and enable the **Google Calendar API**.
2. Under **APIs & Services → Credentials**, create an **OAuth 2.0 Client ID** of type "Web application".
3. Add `http://localhost:8000/auth/google/callback` as an authorized redirect URI.
4. Create a `.env` file in the project folder (it's already in `.gitignore`, so it won't be committed) with:
   ```
   GOOGLE_CLIENT_ID=your-client-id
   GOOGLE_CLIENT_SECRET=your-client-secret
   GOOGLE_REDIRECT_URI=http://localhost:8000/auth/google/callback
   ```
5. Start the server, open **Settings**, and press **Connect Google Calendar**.

The access and refresh tokens are stored locally in `settings.json` under the `googleCalendar` key. Nothing is sent anywhere except directly to Google's own servers.

**Important:** never commit your real `.env` file or share your client secret. If it's ever exposed accidentally, regenerate it in the Google Cloud Console.

---

# Notes

- The server currently must be running locally for settings to save and load properly, but I am still trying to change this
- Settings are only stored locally, nothing is sent to any external server

# Contact

You have questions, feedback or inspirations? Feel free to contact me at
tx.9394.tx@outlook.de
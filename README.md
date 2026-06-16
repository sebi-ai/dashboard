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
The python server exposes to endpoints used by the frontend:

Method  |   Path    |   Description
--------|-----------|---------------------------------- 
POST    | /save     | Save settings in settings.json
GET     | /load     | Returns to current settings.json

All other GET requests are served as static file (HTML, CSS, JS).

---

# Notes

- The server currently must be running locally for settings to save and load properly, but I am still trying to change this
- Settings are only stored locally, nothing is sent to any external server

# Contact

You have questions, feedback or inspirations? Feel free to contact me at
tx.9394.tx@outlook.de

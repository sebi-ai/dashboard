# Stardance Dashboard (Native)

This workspace contains two UI options:

- `app.py` — Streamlit web UI (kept for reference)
- `app_gui.py` — Native desktop app using PySide6 (recommended)

Quick start

1. Create and activate a Python virtual environment.
2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Run the native app:

```bash
python app_gui.py
```

Features

- Large clock prominently displayed.
- Compact weather summary on the right.
- Manual `Refresh now` button.
- Auto update interval selectable (`10s`, `30s`, `60s`, `Manual only`).
- Font size options: `Small`, `Medium`, `Large`.
- Minimize to system tray — right-click tray icon to restore or exit.

Building a single executable (Windows)

Install PyInstaller in your environment:

```powershell
pip install pyinstaller
```

Then run the provided PowerShell build script:

```powershell
.\build_exe.ps1
```

Notes

- The app fetches location from `ipwho.is` and weather from Open‑Meteo. Be mindful of API rate limits if you set a very short update interval.
- If you want a different look or additional functionality (tray icon image, persistent settings, localization), tell me and I will implement it.

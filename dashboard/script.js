const API_BASE = window.location.protocol === "file:" ? "http://localhost:8000" : window.location.origin;

const FORBIDDEN_FILES = ['.env', 'client_secret', '.json', 'settings.json'];
if (FORBIDDEN_FILES.some(file => window.location.pathname.includes(file))) {
 console.warn('Access to sensitive file blocked');
 window.location.href = '/index.html';
}

const connectBtn = document.getElementById('connect-google-calendar-btn');
const disconnectBtn = document.getElementById('disconnect-google-calendar-btn');
const calendarStatus = document.getElementById('calendar-connection-status');
const eventsList = document.getElementById('calendar-events-list');

const connectMailBtn = document.getElementById('connect-google-mail-btn');
const disconnectMailBtn = document.getElementById('disconnect-google-mail-btn');
const notificationsStatus = document.getElementById('notifications-connection-status');
const messagesList = document.getElementById('notifications-messages-list');

let stockCryptoSelection = null;

const WIDGET_KEY_TO_CHECKBOX = {
  weather: "weather-widget",
  dateTime: "date-time-widget",
  notifications: "notifications-widget",
  countdown: "countdown-widget",
  calendar: "calendar-widget",
  stockCrypto: "stock-crypto-widget",
};

const WIDGET_KEY_TO_LABEL = {
  weather: "Weather",
  dateTime: "Date & Time",
  notifications: "Notifications",
  countdown: "Countdown to Date",
  calendar: "Calendar",
  stockCrypto: "Stock/Crypto Prices",
};

// Google Calendar + Gmail are connected through the local server (server.py).
// The server owns the OAuth flow and stores the tokens in settings.json, so
// both this website and the Python dashboard (dashboard.py) can use them.
async function startGoogleConnect() {
 if (window.location.protocol === 'file:') {
 showNotification('ERROR: Open via http://localhost:8000, not by double-clicking the file!', 'error');
 return;
 }
 try {
 const res = await fetch(`${API_BASE}/auth/google`);
 const data = await res.json().catch(() => null);
 if (res.ok && data && data.url) {
 window.location.href = data.url;
 } else {
 showNotification(data?.error || 'Google OAuth is not configured on the server. See the README for .env setup.', 'error');
 }
 } catch (e) {
 showNotification('Server not reachable - is server.py running?', 'error');
 }
}

if (connectBtn) {
 connectBtn.addEventListener('click', startGoogleConnect);
}

if (connectMailBtn) {
 connectMailBtn.addEventListener('click', startGoogleConnect);
}

async function disconnectGoogle() {
 try {
 await fetch(`${API_BASE}/calendar/disconnect`, { method: 'POST' });
 } catch (e) {
 // The token is removed server-side; ignore network errors here.
 }
 showNotification('Google account disconnected.');
 refreshCalendarStatus();
 refreshNotificationsStatus();
}

if (disconnectBtn) {
 disconnectBtn.addEventListener('click', disconnectGoogle);
}

if (disconnectMailBtn) {
 disconnectMailBtn.addEventListener('click', disconnectGoogle);
}

async function refreshCalendarStatus() {
 if (!calendarStatus) return;
 try {
 const res = await fetch(`${API_BASE}/calendar/status`);
 const data = await res.json().catch(() => null);
 const connected = !!(res.ok && data && data.connected);
 if (connected) {
 calendarStatus.textContent = "Connected to Google Calendar.";
 if (connectBtn) connectBtn.style.display = "none";
 if (disconnectBtn) disconnectBtn.style.display = "inline-block";
 loadCalendarEvents();
 } else {
 calendarStatus.textContent = "Not connected.";
 if (connectBtn) connectBtn.style.display = "inline-block";
 if (disconnectBtn) disconnectBtn.style.display = "none";
 if (eventsList) eventsList.innerHTML = "";
 }
 } catch (e) {
 calendarStatus.textContent = "Server not reachable.";
 }
}

async function loadCalendarEvents() {
 if (!eventsList) return;
 try {
 const res = await fetch(`${API_BASE}/calendar/events`);
 if (res.status === 401) {
 eventsList.innerHTML = "<li>Not connected to Google Calendar.</li>";
 return;
 }
 if (!res.ok) {
 const data = await res.json().catch(() => null);
 eventsList.innerHTML = `<li>${data?.error || "Failed to load events."}</li>`;
 return;
 }
 const data = await res.json();
 const items = data.events || [];
 eventsList.innerHTML = "";
 if (items.length === 0) {
 eventsList.innerHTML = "<li>No upcoming events.</li>";
 return;
 }
 items.forEach(event => {
 const li = document.createElement("li");
 const start = event.start?.dateTime || event.start?.date || "";
 const startLabel = start ? new Date(start).toLocaleString() : "";
 li.textContent = `${startLabel} — ${event.summary ?? "(no title)"}`;
 eventsList.appendChild(li);
 });
 } catch (e) {
 eventsList.innerHTML = "<li>Failed to load events.</li>";
 console.error('Error loading calendar events:', e);
 }
}

async function refreshNotificationsStatus() {
 if (!notificationsStatus) return;
 try {
 const res = await fetch(`${API_BASE}/calendar/status`);
 const data = await res.json().catch(() => null);
 const connected = !!(res.ok && data && data.connected);
 if (connected) {
 notificationsStatus.textContent = "Connected to Google Mail.";
 if (connectMailBtn) connectMailBtn.style.display = "none";
 if (disconnectMailBtn) disconnectMailBtn.style.display = "inline-block";
 loadMessages();
 } else {
 notificationsStatus.textContent = "Not connected.";
 if (connectMailBtn) connectMailBtn.style.display = "inline-block";
 if (disconnectMailBtn) disconnectMailBtn.style.display = "none";
 if (messagesList) messagesList.innerHTML = "";
 }
 } catch (e) {
 notificationsStatus.textContent = "Server not reachable.";
 }
}

async function loadMessages() {
 if (!messagesList) return;
 try {
 const res = await fetch(`${API_BASE}/notifications/messages`);
 if (res.status === 401) {
 messagesList.innerHTML = "<li>Not connected to Google Mail.</li>";
 return;
 }
 if (res.status === 403) {
 messagesList.innerHTML = "<li>Missing Gmail permission. Disconnect and reconnect your Google account.</li>";
 return;
 }
 if (!res.ok) {
 const data = await res.json().catch(() => null);
 messagesList.innerHTML = `<li>${data?.error || "Failed to load messages."}</li>`;
 return;
 }
 const data = await res.json();
 const messages = data.messages || [];
 messagesList.innerHTML = "";
 if (messages.length === 0) {
 messagesList.innerHTML = "<li>No messages found.</li>";
 return;
 }
 messages.forEach(msg => {
 // Build with text nodes, not innerHTML: email subjects/senders are
 // attacker-controlled and must never be parsed as HTML.
 const li = document.createElement("li");
 const subject = document.createElement("strong");
 subject.textContent = msg.subject || "(no subject)";
 li.appendChild(subject);
 li.appendChild(document.createElement("br"));
 li.appendChild(document.createTextNode(msg.from || "(unknown sender)"));
 li.appendChild(document.createElement("br"));
 const snippet = document.createElement("small");
 snippet.textContent = msg.snippet || "";
 li.appendChild(snippet);
 messagesList.appendChild(li);
 });
 } catch (e) {
 messagesList.innerHTML = "<li>Failed to load messages.</li>";
 console.error('Error loading messages:', e);
 }
}

function handleGoogleRedirectParams() {
 const url = new URL(window.location.href);
 if (url.searchParams.has('google_connected')) {
 showNotification('Google account connected!', 'success');
 }
 if (url.searchParams.has('google_error')) {
 showNotification(`Google error: ${url.searchParams.get('google_error')}`, 'error');
 }
 if (url.searchParams.has('code') || url.searchParams.has('error') ||
     url.searchParams.has('google_connected') || url.searchParams.has('google_error')) {
 window.history.replaceState({}, '', url.pathname + url.hash);
 }
}

async function loadSettings() {
 try {
 const res = await fetch(`${API_BASE}/load`);
 if (!res.ok) return;
 const s = await res.json();

 if (s.location) document.getElementById("location").value = s.location;
 if (s.useIpLocation) {
 document.getElementById("use-ip-location").checked = true;
 document.getElementById("location").disabled = true;
 }

 if (s.widgets) {
    for (const [key, value] of Object.entries(s.widgets)) {
      const id = WIDGET_KEY_TO_CHECKBOX[key];
      if (id) document.getElementById(id).checked = value;
    }
  }

 // Restore the saved countdown date, otherwise opening Settings and pressing
 // Save silently wipes the date (the input would be sent back as "").
 if (s.countdownDate) document.getElementById("countdown-date").value = s.countdownDate;

 if (s.widgetLayout) {
   layoutState = { cells: normalizeSavedCells(s.widgetLayout) };
 } else {
   layoutState = { cells: {} };
 }
 renderLayoutEditor();

 if (s.theme) document.getElementById("theme-select").value = s.theme;
 if (s.customColor) document.getElementById("custom-color").value = s.customColor;
 if (s.themeMode === "custom") {
 document.getElementById("theme-mode-custom").checked = true;
 document.getElementById("theme-mode-preset").checked = false;
 } else if (s.themeMode === "preset") {
 document.getElementById("theme-mode-preset").checked = true;
 document.getElementById("theme-mode-custom").checked = false;
 }
 document.getElementById("theme-select").disabled =
 document.getElementById("theme-mode-custom").checked;
 document.getElementById("custom-color").disabled =
 document.getElementById("theme-mode-preset").checked;

 if (s.stockCryptoSelection) {
 stockCryptoSelection = s.stockCryptoSelection;
 renderStockCryptoSelection();
 }

 } catch (e) {
 console.log("No saved settings found.");
 }
}

async function getCoordinates(locationName) {
 const url = `https://nominatim.openstreetmap.org/search?q=${encodeURIComponent(locationName)}&format=json&limit=1`;
 const res = await fetch(url, { headers: { "Accept-Language": "en" } });
 const data = await res.json();

 if (data.length === 0) return null;

 return {
 lat: data[0].lat,
 lon: data[0].lon,
 displayName: data[0].display_name
 };
}

async function getIpLocation() {
 const res = await fetch("https://ipapi.co/json/");
 const data = await res.json();
 return {
 lat: data.latitude,
 lon: data.longitude,
 displayName: data.city + ", " + data.country_name
 };
}

function showSection(sectionId) {
 const homeSection = document.getElementById("home");
 if (homeSection) homeSection.style.display = sectionId === "home" ? "block" : "none";
}

function goHome() {
 const homeSection = document.getElementById("home");

 if (homeSection) {
 showSection("home");
 window.location.hash = "home";
 window.scrollTo({ top: 0, behavior: "smooth" });
 return;
 }

 window.location.href = "/index.html#home";
}

function initializeHomeView() {
 if (!document.getElementById("home")) {
 return;
 }

 showSection("home");
 window.scrollTo(0, 0);
}

document.getElementById("redirect-start-btn").addEventListener("click", function(e) {
 e.preventDefault();
 window.location.href = "/dashboard.html";
});

document.getElementById("home-btn").addEventListener("click", function(e) {
 e.preventDefault();
 goHome();
});

document.getElementById("settings-btn").addEventListener("click", function(e) {
 e.preventDefault();
 window.location.href = "/settings.html";
});

document.getElementById("about-btn").addEventListener("click", function(e) {
 e.preventDefault();
 window.location.href = "/about.html";
});

const checkbox = document.getElementById("use-ip-location");
const textfield = document.getElementById("location");
if (checkbox && textfield) {
 checkbox.addEventListener("change", function() {
 textfield.disabled = checkbox.checked;
 });
}

const themeModePreset = document.getElementById("theme-mode-preset");
const themeModeCustom = document.getElementById("theme-mode-custom");
const themeSelect = document.getElementById("theme-select");
const customColorInput = document.getElementById("custom-color");

if (themeModePreset && themeModeCustom && themeSelect && customColorInput) {
 themeSelect.disabled = themeModeCustom.checked;
 customColorInput.disabled = themeModePreset.checked;

 themeModePreset.addEventListener("change", () => {
 if (themeModePreset.checked) {
 themeModeCustom.checked = false;
 }
 themeSelect.disabled = themeModeCustom.checked;
 customColorInput.disabled = themeModePreset.checked;
 });

 themeModeCustom.addEventListener("change", () => {
 if (themeModeCustom.checked) {
 themeModePreset.checked = false;
 }
 themeSelect.disabled = themeModeCustom.checked;
 customColorInput.disabled = themeModePreset.checked;
 });
}// --- Free-form "Align Widgets" editor --------------------------------------
//
// The dashboard is laid out with free-form rectangles (percent of the area).
// The editor is a mini-map: drag a card by its body to MOVE it, and pull a
// corner handle to RESIZE it — fully continuous, no snapping. When a card
// grows into another, the other card is pushed out of the way (and shrinks
// against the wall if needed) so everything always fits on screen.
// Everything updates live from the checkboxes above, even before saving.

let layoutState = { cells: {} };

const MIN_CARD = 20;    // minimum card size in percent (content must stay readable)
// Every OTHER card must stay at least this big after a move/resize. Must be
// <= MIN_CARD: if it were larger, a card resized down to its minimum would
// make every subsequent move/resize fail its constraint check and freeze the
// whole layout.
const MIN_VISIBLE = MIN_CARD;

function activeWidgetKeys() {
  return Object.entries(WIDGET_KEY_TO_CHECKBOX)
    .filter(([key, id]) => document.getElementById(id)?.checked)
    .map(([key]) => key);
}

function autoLayoutCells(preset, keys) {
  const n = keys.length;
  const cells = {};
  if (n === 1) {
    cells[keys[0]] = { x: 0, y: 0, w: 100, h: 100 };
    return cells;
  }
  if (preset === "twoUnequal") {
    // First widget: tall left column. Rest: stacked on the right.
    if (n) cells[keys[0]] = { x: 0, y: 0, w: 45, h: 100 };
    const nrows = Math.max(1, n - 1);
    keys.slice(1).forEach((k, i) => {
      cells[k] = { x: 46, y: (100 * i) / nrows, w: 54, h: 100 / nrows };
    });
  } else if (preset === "threeColumns" || preset === "threeUnequal") {
    const cols = preset === "threeColumns" ? [33, 33, 34] : [25, 45, 30];
    const nrows = Math.max(1, Math.ceil(n / 3));
    keys.forEach((k, i) => {
      const cx = cols.slice(0, i % 3).reduce((a, b) => a + b, 0);
      cells[k] = { x: cx, y: (100 * Math.floor(i / 3)) / nrows, w: cols[i % 3], h: 100 / nrows };
    });
  } else {
    // quadrants: 2x2, grows by adding rows of two
    const nrows = Math.max(2, Math.ceil(n / 2));
    keys.forEach((k, i) => {
      cells[k] = { x: (i % 2) * 50, y: (100 * Math.floor(i / 2)) / nrows, w: 50, h: 100 / nrows };
    });
  }
  return cells;
}

// 0.01% of the map — tolerates the tiny float slivers that reflow math
// (push/shrink/fillGaps) leaves between cards that are supposed to touch.
const EPS = 0.01;

function rectsOverlap(a, b) {
  return a.x < b.x + b.w - EPS && a.x + a.w > b.x + EPS &&
         a.y < b.y + b.h - EPS && a.y + a.h > b.y + EPS;
}

function clampRect(r) {
  r.w = Math.max(r.w, MIN_CARD);
  r.h = Math.max(r.h, MIN_CARD);
  if (r.x < 0) r.x = 0;
  if (r.y < 0) r.y = 0;
  if (r.x + r.w > 100) r.x = 100 - r.w;
  if (r.y + r.h > 100) r.y = 100 - r.h;
}

// Shrink `victim` out of `blocker` as a last resort: keep the largest strip of
// the victim that does not touch the blocker and is at least MIN_CARD in both
// dimensions. Returns true if the victim moved. If nothing qualifies the
// victim keeps its size — the drag cap (fitsOthers) rejects such positions
// anyway, so a card can never be shrunk into an invisible sliver.
function shrinkOut(blocker, victim) {
  const b = blocker, v = victim;
  const strips = [];
  if (b.y > v.y) strips.push({ y: v.y, h: b.y - v.y });                                 // top strip
  if (v.y + v.h > b.y + b.h) strips.push({ y: b.y + b.h, h: v.y + v.h - (b.y + b.h) }); // bottom strip
  if (b.x > v.x) strips.push({ x: v.x, w: b.x - v.x });                                 // left strip
  if (v.x + v.w > b.x + b.w) strips.push({ x: b.x + b.w, w: v.x + v.w - (b.x + b.w) }); // right strip
  let best = null;
  for (const s of strips) {
    const w = s.w !== undefined ? s.w : v.w;
    const h = s.h !== undefined ? s.h : v.h;
    if (w < MIN_CARD || h < MIN_CARD) continue;
    const area = w * h;
    if (!best || area > best.area) best = { ...s, area };
  }
  if (!best) return false;
  if (best.h !== undefined) {
    v.y = best.y;
    v.h = best.h;
  } else {
    v.x = best.x;
    v.w = best.w;
  }
  return true;
}

// Push `victim` out of `blocker`. Tries directions in preference order
// (down, right, up, left); the first one that fully resolves the overlap and
// stays on the map wins. Returns true if the victim moved.
function pushOut(blocker, victim) {
  const tries = [
    { x: victim.x, y: blocker.y + blocker.h }, // down
    { x: blocker.x + blocker.w, y: victim.y }, // right
    { x: victim.x, y: blocker.y - victim.h },  // up
    { x: blocker.x - victim.w, y: victim.y },  // left
  ];
  for (const t of tries) {
    if (t.x >= -0.001 && t.y >= -0.001 && t.x + victim.w <= 100.001 && t.y + victim.h <= 100.001 &&
        !rectsOverlap(blocker, { x: t.x, y: t.y, w: victim.w, h: victim.h })) {
      victim.x = t.x;
      victim.y = t.y;
      return true;
    }
  }
  return false;
}

// Push every card that overlaps the dragged card out of the way, cascading
// through the whole layout (a pushed card can knock its own neighbours) until
// everything fits, shrinking against the wall only as a last resort. The card
// being dragged is never pushed or shrunk itself.
// Works on a supplied cells map (defaults to the live layout) so it can be
// simulated on a copy for constraint checks.
function resolveOverlaps(moved, cells) {
  const map = cells || layoutState.cells;
  const others = Object.values(map).filter(c => c !== moved);
  // Phase 1: cascade pushes.
  for (let pass = 0; pass < 20; pass++) {
    let changed = false;
    for (const b of others) {
      if (rectsOverlap(moved, b) && pushOut(moved, b)) changed = true;
    }
    for (let i = 0; i < others.length; i++) {
      for (let j = i + 1; j < others.length; j++) {
        if (rectsOverlap(others[i], others[j]) && pushOut(others[i], others[j])) changed = true;
      }
    }
    if (!changed) break;
  }
  // Phase 2: force-clean whatever still overlaps by shrinking the pushed card
  // out of the blocker. Never shrinks the dragged card, never drops a card
  // below MIN_CARD.
  for (let pass = 0; pass < 10; pass++) {
    let changed = false;
    for (const b of others) {
      if (rectsOverlap(moved, b) && shrinkOut(moved, b)) changed = true;
    }
    for (let i = 0; i < others.length; i++) {
      for (let j = i + 1; j < others.length; j++) {
        if (rectsOverlap(others[i], others[j]) && shrinkOut(others[i], others[j])) changed = true;
      }
    }
    if (!changed) break;
  }
  // Phase 3: a card that STILL overlaps cannot be pushed or shrunk where it
  // is — relocate it (never the dragged card) to the largest genuinely free
  // spot. This always terminates and leaves a clean layout whenever any
  // usable free space exists, which is what keeps heavily-packed layouts from
  // accumulating invisible overlaps.
  const allKeys = Object.keys(map);
  for (let pass = 0; pass < 6; pass++) {
    let changed = false;
    for (let i = 0; i < allKeys.length; i++) {
      for (let j = i + 1; j < allKeys.length; j++) {
        const a = map[allKeys[i]];
        const b = map[allKeys[j]];
        if (!rectsOverlap(a, b)) continue;
        const victim = (b === moved) ? a : b;
        const occupied = Object.values(map).filter(c => c !== victim);
        const free = largestFreeRect(occupied);
        if (free) {
          victim.x = free.x;
          victim.y = free.y;
          victim.w = free.w;
          victim.h = free.h;
          changed = true;
        }
      }
    }
    if (!changed) break;
  }
}

// After a card is moved or resized, expand every card (except the one the
// user is actively dragging) into any empty space that was left behind, so
// the layout always fills the screen and no dead gaps remain.
function fillGaps(exceptKey, cells) {
  const map = cells || layoutState.cells;
  const keys = Object.keys(map).filter(k => k !== exceptKey);
  for (let pass = 0; pass < 8; pass++) {
    let changed = false;
    for (const key of keys) {
      const r = map[key];
      if (!r) continue;
      // Expand downward: the nearest card that shares our horizontal span and
      // starts below us limits how far we can grow.
      let maxBottom = 100;
      for (const o of Object.values(map)) {
        if (o === r) continue;
        if (r.x < o.x + o.w - 0.01 && r.x + r.w > o.x + 0.01 && o.y >= r.y + r.h - 0.01) {
          maxBottom = Math.min(maxBottom, o.y);
        }
      }
      if (r.y + r.h < maxBottom - 0.01) {
        r.h = maxBottom - r.y;
        changed = true;
      }
      // Expand rightward: the nearest card that shares our vertical span and
      // starts to the right of us limits how far we can grow.
      let maxRight = 100;
      for (const o of Object.values(map)) {
        if (o === r) continue;
        if (r.y < o.y + o.h - 0.01 && r.y + r.h > o.y + 0.01 && o.x >= r.x + r.w - 0.01) {
          maxRight = Math.min(maxRight, o.x);
        }
      }
      if (r.x + r.w < maxRight - 0.01) {
        r.w = maxRight - r.x;
        changed = true;
      }
      // Expand upward: the nearest card above us that shares our horizontal
      // span limits how far we can grow.
      let minTop = 0;
      for (const o of Object.values(map)) {
        if (o === r) continue;
        if (r.x < o.x + o.w - 0.01 && r.x + r.w > o.x + 0.01 && o.y + o.h <= r.y + 0.01) {
          minTop = Math.max(minTop, o.y + o.h);
        }
      }
      if (r.y > minTop + 0.01) {
        r.h += r.y - minTop;
        r.y = minTop;
        changed = true;
      }
      // Expand leftward: the nearest card to our left that shares our
      // vertical span limits how far we can grow.
      let minLeft = 0;
      for (const o of Object.values(map)) {
        if (o === r) continue;
        if (r.y < o.y + o.h - 0.01 && r.y + r.h > o.y + 0.01 && o.x + o.w <= r.x + 0.01) {
          minLeft = Math.max(minLeft, o.x + o.w);
        }
      }
      if (r.x > minLeft + 0.01) {
        r.w += r.x - minLeft;
        r.x = minLeft;
        changed = true;
      }
    }
    if (!changed) break;
  }
}

// Interpolate the moving edges of a resize between the original rect and the
// proposed rect, by fraction t in [0, 1]. Used to find the largest size that
// still keeps every other card visible.
function cornerLerp(orig, proposed, corner, t) {
  const r = {};
  r.x = orig.x + (proposed.x - orig.x) * t;
  r.y = orig.y + (proposed.y - orig.y) * t;
  r.w = orig.w + (proposed.w - orig.w) * t;
  r.h = orig.h + (proposed.h - orig.h) * t;
  clampRect(r);
  return r;
}

// True if, with the dragged card at rect r, the whole map can settle cleanly:
// no two cards overlap (a card under another one would be invisible), and
// every OTHER card stays at least MIN_VISIBLE wide and tall.
function fitsOthers(r, key) {
  const cells = {};
  for (const [k, v] of Object.entries(layoutState.cells)) cells[k] = { ...v };
  cells[key] = { ...r };
  resolveOverlaps(cells[key], cells);
  const vals = Object.values(cells);
  for (let i = 0; i < vals.length; i++) {
    for (let j = i + 1; j < vals.length; j++) {
      if (rectsOverlap(vals[i], vals[j])) return false;
    }
  }
  for (const [k, v] of Object.entries(cells)) {
    if (k === key) continue;
    if (v.w < MIN_VISIBLE || v.h < MIN_VISIBLE) return false;
  }
  return true;
}

// Clamp a resize so the dragged card can never grow big enough to hide any
// other card: binary-search between the original and proposed rects for the
// largest size where every other card keeps at least MIN_VISIBLE.
function capForOthers(proposed, key, orig, corner) {
  if (fitsOthers(proposed, key)) return proposed;
  let lo = 0;
  let hi = 1;
  for (let i = 0; i < 12; i++) {
    const mid = (lo + hi) / 2;
    const test = cornerLerp(orig, proposed, corner, mid);
    if (fitsOthers(test, key)) lo = mid;
    else hi = mid;
  }
  return cornerLerp(orig, proposed, corner, lo);
}

// Largest empty axis-aligned rectangle on the map (used to place new widgets
// when the regular 2xN slots are all taken, and to relocate cards that end up
// stuck). Any maximal free rectangle has its edges flush against occupied
// cards or the map border, so it is enough to check every candidate bounded
// by those coordinates.
function largestFreeRect(occupied) {
  const xs = [0, 100, ...occupied.map(r => r.x), ...occupied.map(r => r.x + r.w)];
  const ys = [0, 100, ...occupied.map(r => r.y), ...occupied.map(r => r.y + r.h)];
  const ux = [...new Set(xs)].sort((a, b) => a - b);
  const uy = [...new Set(ys)].sort((a, b) => a - b);
  let best = null;
  for (const x0 of ux) {
    for (const x1 of ux) {
      if (x1 <= x0) continue;
      const w = x1 - x0;
      if (w < MIN_CARD) continue;
      for (const y0 of uy) {
        for (const y1 of uy) {
          if (y1 <= y0) continue;
          const h = y1 - y0;
          if (h < MIN_CARD) continue;
          if (best && w * h <= best.w * best.h) continue;
          const rect = { x: x0, y: y0, w, h };
          if (occupied.some(o => rectsOverlap(o, rect))) continue;
          best = rect;
        }
      }
    }
  }
  return best;
}

function placeNewWidget(key, keys) {
  // Newly-enabled widget goes into the first free spot of a 2xN grid.
  const existing = Object.values(layoutState.cells);
  const nrows = Math.max(2, Math.ceil(keys.length / 2));
  for (let r = 0; r < nrows; r++) {
    for (let c = 0; c < 2; c++) {
      const slot = { x: c * 50, y: (100 * r) / nrows, w: 50, h: 100 / nrows };
      if (!existing.some(e => rectsOverlap(e, slot))) {
        layoutState.cells[key] = slot;
        return;
      }
    }
  }
  // Fall back to the largest genuinely free rectangle, so the new card is
  // always visible and never covers an existing one.
  const free = largestFreeRect(existing);
  if (free) {
    layoutState.cells[key] = free;
    return;
  }
  // The map is completely packed: reflow everything so the new widget can
  // actually be seen. (Rare — the layout is saved as soon as the user edits.)
  layoutState.cells = autoLayoutCells("twoUnequal", keys);
}

function syncLayoutWithWidgets(keys) {
  for (const key of Object.keys(layoutState.cells)) {
    if (!keys.includes(key)) delete layoutState.cells[key];
  }
  if (Object.keys(layoutState.cells).length === 0) {
    layoutState.cells = autoLayoutCells("twoUnequal", keys);
    return;
  }
  for (const key of keys) {
    if (!layoutState.cells[key]) placeNewWidget(key, keys);
  }
}

// DOM element for each enabled widget, so dragging can update styles directly
// instead of rebuilding the whole editor on every pointermove.
const layoutCellElements = new Map();

function renderLayoutEditor() {
  const grid = document.getElementById("layout-grid");
  const hint = document.getElementById("layout-hint");
  if (!grid) return;

  const keys = activeWidgetKeys();
  if (keys.length === 0) {
    grid.innerHTML = "";
    layoutCellElements.clear();
    if (hint) hint.style.display = "block";
    return;
  }
  if (hint) hint.style.display = "none";

  syncLayoutWithWidgets(keys);

  // A newly-added widget can land on top of existing cards; push everything
  // apart so no card is ever hidden behind another.
  if (keys.length > 1) {
    resolveOverlaps(layoutState.cells[keys[0]]);
  }

  // Reconcile the DOM with the active widget set: remove cards for disabled
  // widgets, create cards for newly enabled ones, keep the rest untouched.
  for (const [key, el] of layoutCellElements) {
    if (!keys.includes(key)) {
      el.remove();
      layoutCellElements.delete(key);
    }
  }
  for (const key of keys) {
    if (layoutCellElements.has(key)) continue;
    const el = document.createElement("div");
    el.className = "layout-cell";
    el.dataset.key = key;
    el.textContent = WIDGET_KEY_TO_LABEL[key] || key;

    // Windows-11-style corner resize handles (faint by default, full on hover).
    ["tl", "tr", "bl", "br"].forEach(corner => {
      const h = document.createElement("span");
      h.className = "layout-handle layout-handle-" + corner;
      h.dataset.corner = corner;
      el.appendChild(h);
    });

    grid.appendChild(el);
    layoutCellElements.set(key, el);
  }

  applyLayout();
}

// Update positions/sizes of the existing cards without rebuilding the DOM —
// this is what keeps dragging and resizing smooth.
function applyLayout() {
  for (const [key, el] of layoutCellElements) {
    const r = layoutState.cells[key];
    if (!r) continue;
    el.style.left = r.x + "%";
    el.style.top = r.y + "%";
    el.style.width = r.w + "%";
    el.style.height = r.h + "%";
  }
}

// Normalize saved cells: keep free-form rects, convert legacy grid cells.
function normalizeSavedCells(wl) {
  const cells = wl.cells || {};
  const columns = (wl.columns || []).filter(v => typeof v === "number" && v > 0);
  const rows = (wl.rows || []).filter(v => typeof v === "number" && v > 0);
  const out = {};
  for (const [key, cell] of Object.entries(cells)) {
    if (cell && typeof cell.x === "number" && typeof cell.y === "number" &&
        typeof cell.w === "number" && typeof cell.h === "number") {
      out[key] = { x: cell.x, y: cell.y, w: cell.w, h: cell.h };
    } else if (cell && columns.length && rows.length &&
               typeof cell.c === "number" && typeof cell.r === "number") {
      const ncols = columns.length;
      const nrows = rows.length;
      const c = cell.c;
      const r = cell.r;
      const cs = Math.max(1, cell.cs || 1);
      const rs = Math.max(1, cell.rs || 1);
      if (c < 0 || r < 0 || c + cs > ncols || r + rs > nrows) continue;
      const colTotal = columns.reduce((a, b) => a + b, 0);
      const rowTotal = rows.reduce((a, b) => a + b, 0);
      out[key] = {
        x: (columns.slice(0, c).reduce((a, b) => a + b, 0) / colTotal) * 100,
        w: (columns.slice(c, c + cs).reduce((a, b) => a + b, 0) / colTotal) * 100,
        y: (rows.slice(0, r).reduce((a, b) => a + b, 0) / rowTotal) * 100,
        h: (rows.slice(r, r + rs).reduce((a, b) => a + b, 0) / rowTotal) * 100,
      };
    }
  }
  return out;
}

// Move a card freely by dragging its body.
function startMove(cell, e) {
  e.preventDefault();
  e.stopPropagation();
  const map = document.getElementById("layout-map");
  const rect = map.getBoundingClientRect();
  const key = cell.dataset.key;
  const orig = { ...layoutState.cells[key] };
  const startX = e.clientX;
  const startY = e.clientY;
  cell.classList.add("layout-moving");
  try { map.setPointerCapture(e.pointerId); } catch (_) { /* not supported */ }

  function onMove(ev) {
    const dx = ((ev.clientX - startX) / rect.width) * 100;
    const dy = ((ev.clientY - startY) / rect.height) * 100;
    const proposed = { ...orig };
    proposed.x = orig.x + dx;
    proposed.y = orig.y + dy;
    clampRect(proposed);
    // The dragged card must never end up covering another card: cap the
    // position the same way a resize caps the size.
    const settled = capForOthers(proposed, key, orig, null);
    layoutState.cells[key] = settled;
    resolveOverlaps(settled);
    applyLayout();
  }
  function onUp() {
    document.removeEventListener("pointermove", onMove);
    document.removeEventListener("pointerup", onUp);
    try { map.releasePointerCapture(e.pointerId); } catch (_) { /* not supported */ }
    cell.classList.remove("layout-moving");
    fillGaps(key);
    renderLayoutEditor();
  }
  document.addEventListener("pointermove", onMove);
  document.addEventListener("pointerup", onUp);
}

// Free-form corner resize: pull a corner to any size, no snapping.
function startCornerResize(cell, corner, e) {
  e.preventDefault();
  e.stopPropagation();
  const map = document.getElementById("layout-map");
  const rect = map.getBoundingClientRect();
  const key = cell.dataset.key;
  const orig = { ...layoutState.cells[key] };
  cell.classList.add("layout-resizing");
  try { map.setPointerCapture(e.pointerId); } catch (_) { /* not supported */ }

  function onMove(ev) {
    const gx = Math.max(0, Math.min(100, ((ev.clientX - rect.left) / rect.width) * 100));
    const gy = Math.max(0, Math.min(100, ((ev.clientY - rect.top) / rect.height) * 100));
    const proposed = { ...orig };
    if (corner === "br") {
      proposed.w = gx - orig.x;
      proposed.h = gy - orig.y;
    } else if (corner === "tl") {
      proposed.w = orig.x + orig.w - gx;
      proposed.h = orig.y + orig.h - gy;
      proposed.x = gx;
      proposed.y = gy;
    } else if (corner === "tr") {
      proposed.y = gy;
      proposed.h = orig.y + orig.h - gy;
      proposed.w = gx - orig.x;
    } else { // bl: keeps the top-right corner fixed
      proposed.x = gx;
      proposed.w = orig.x + orig.w - gx;
      proposed.h = gy - orig.y;
    }
    clampRect(proposed);
    // Never let one card grow so big that it hides every other card.
    const capped = capForOthers(proposed, key, orig, corner);
    layoutState.cells[key] = capped;
    resolveOverlaps(capped);
    applyLayout();
  }
  function onUp() {
    document.removeEventListener("pointermove", onMove);
    document.removeEventListener("pointerup", onUp);
    try { map.releasePointerCapture(e.pointerId); } catch (_) { /* not supported */ }
    cell.classList.remove("layout-resizing");
    fillGaps(key);
    renderLayoutEditor();
  }
  document.addEventListener("pointermove", onMove);
  document.addEventListener("pointerup", onUp);
}

// Pointer interactions on the mini-map: body drag moves, corner handles resize.
const layoutGridInteract = document.getElementById("layout-grid");
if (layoutGridInteract) {
  layoutGridInteract.addEventListener("pointerdown", e => {
    const handle = e.target.closest(".layout-handle");
    if (handle) {
      const cell = handle.closest(".layout-cell");
      if (cell) startCornerResize(cell, handle.dataset.corner, e);
      return;
    }
    const cell = e.target.closest(".layout-cell");
    if (cell) startMove(cell, e);
  });
}

// Widget checkboxes update the layout editor live (no 3-widget limit).
document.querySelectorAll(".limited-checkbox").forEach(checkbox => {
  checkbox.addEventListener("change", renderLayoutEditor);
});

renderLayoutEditor();
if (document.getElementById("location")) {
 loadSettings();
}

window.addEventListener("load", initializeHomeView);

const notification = document.getElementById("site-notification");
const notificationText = notification.querySelector(".site-notification__text");
let notificationTimer;

function showNotification(message, type = "info") {
 clearTimeout(notificationTimer);

 notificationText.textContent = message;

 notification.className = "site-notification";
 notification.classList.add("site-notification-visible");
 notification.classList.add(`site-notification--${type}`);

 notificationTimer = setTimeout(() => {
 notification.className = "site-notification";
 }, 3000);
}

const locationInput = document.getElementById("location");
const suggestionsList = document.getElementById("location-suggestions");
let debounceTimer;

if (locationInput && suggestionsList) {
 locationInput.addEventListener("input", function() {
 clearTimeout(debounceTimer);
 const query = locationInput.value.trim();

 if (query.length < 3) {
 suggestionsList.innerHTML = "";
 return;
 }

 debounceTimer = setTimeout(async () => {
 const url = `https://nominatim.openstreetmap.org/search?q=${encodeURIComponent(query)}&format=json&limit=5`;
 const res = await fetch(url, { headers: { "Accept-Language": "en" } });
 const data = await res.json();

 suggestionsList.innerHTML = "";
 data.forEach(place => {
 const li = document.createElement("li");
 li.textContent = place.display_name;
 li.addEventListener("click", function() {
 locationInput.value = place.display_name;
 suggestionsList.innerHTML = "";
 });
 suggestionsList.appendChild(li);
 });
 }, 400);
 });
}

document.addEventListener("click", function(e) {
 if (suggestionsList && e.target !== locationInput) {
 suggestionsList.innerHTML = "";
 }
});

const saveSettingsBtn = document.getElementById("save-settings-btn");

if (saveSettingsBtn) {
 saveSettingsBtn.addEventListener("click", async function() {

 const checked = document.querySelectorAll('.limited-checkbox:checked');
 const presetThemeChecked = document.getElementById("theme-mode-preset").checked;
 const customThemeChecked = document.getElementById("theme-mode-custom").checked;
 const location = document.getElementById("location").value;
 const useIp = document.getElementById("use-ip-location").checked;

 if (checked.length === 0) {
 showNotification("Please select at least one widget.", "error");
 return;
 }

 if (!useIp && location.trim() === "") {
 showNotification("Please enter a location or enable IP location.", "error");
 return;
 }

 if (!presetThemeChecked && !customThemeChecked) {
 showNotification("Please select a theme.", "error");
 return;
 }

 let coords = null;
 if (useIp) {
 try {
 coords = await getIpLocation();
 } catch (e) {
 showNotification("Could not determine IP location.", "error");
 return;
 }
 } else {
 coords = await getCoordinates(location);
 if (!coords) {
 showNotification("Location not found. Please try a different name.", "error");
 return;
 }
 }
 const settings = {
 location: location,
 coordinates: coords,
 useIpLocation: useIp,
 widgets: {
 weather: document.getElementById("weather-widget").checked,
 notifications: document.getElementById("notifications-widget").checked,
 dateTime: document.getElementById("date-time-widget").checked,
 countdown: document.getElementById("countdown-widget").checked,
 calendar: document.getElementById("calendar-widget").checked,
 stockCrypto: document.getElementById("stock-crypto-widget").checked,
 },
 theme: presetThemeChecked
 ? document.getElementById("theme-select").value
 : null,
 customColor: customThemeChecked
 ? document.getElementById("custom-color").value
 : null,
 themeMode: customThemeChecked
 ? "custom"
 : (presetThemeChecked ? "preset" : null),    countdownDate: document.getElementById("countdown-date").value,
    stockCryptoSelection: stockCryptoSelection,
    widgetLayout: {
      cells: layoutState.cells,
    }
  };

 try {
 const res = await fetch(`${API_BASE}/save`, {
 method: "POST",
 headers: { "Content-Type": "application/json" },
 body: JSON.stringify(settings)
 });

 if (!res.ok) {
 const errorData = await res.json().catch(() => null);
 showNotification(errorData?.error ?? "Settings could not be saved.", "error");
 return;
 }

 showNotification("Settings saved successfully.", "success");
 } catch (error) {
 console.error("Server not reachable:", error);
 showNotification("Server not reachable. Settings were not saved.", "error");
 }
 });
}

function updateModalOverlay() {
 const modals = [
 document.getElementById("countdown-window"),
 document.getElementById("calendar-window"),
 document.getElementById("notifications-window"),
 document.getElementById("stock-crypto-window")
 ];

 const hasOpenModal = modals.some(modal => modal && modal.style.display === "block");

 if (hasOpenModal) {
 document.body.classList.add("modal-open");
 } else {
 document.body.classList.remove("modal-open");
 }
}

const countdownWidget = document.getElementById("countdown-widget");
const countdownWindow = document.getElementById("countdown-window");
const closeCountdown = document.getElementById("save-countdown");
const countdownDate = document.getElementById("countdown-date");
const openCountdownBtn = document.getElementById("open-countdown-btn");

function openCountdownWindow() {
 if (!countdownWindow) return;
 countdownWindow.style.display = "block";
 updateModalOverlay();
 if (countdownDate) countdownDate.focus();
}

if (countdownWidget) {
 countdownWidget.addEventListener("change", function () {
 if (countdownWidget.checked) {
 openCountdownWindow();
 } else if (countdownDate) {
 countdownDate.value = "";
 }
 });
}

if (openCountdownBtn) {
 openCountdownBtn.addEventListener("click", openCountdownWindow);
}

if (closeCountdown && countdownWindow) {
 closeCountdown.addEventListener("click", function () {
 countdownWindow.style.display = "none";
 updateModalOverlay();
 });
}

if (calendarStatus) {
 handleGoogleRedirectParams();
 refreshCalendarStatus();
}

const calendarWidgetCheckbox = document.getElementById("calendar-widget");
const calendarWindow = document.getElementById("calendar-window");
const closeCalendarWindow = document.getElementById("close-calendar-window");
const openCalendarBtn = document.getElementById("open-calendar-btn");

function openCalendarWindow() {
 if (calendarWindow) {
 calendarWindow.style.display = "block";
 updateModalOverlay();
 }
}

if (calendarWidgetCheckbox) {
 calendarWidgetCheckbox.addEventListener("change", function () {
 if (calendarWidgetCheckbox.checked) {
 openCalendarWindow();
 }
 });
}

if (openCalendarBtn) {
 openCalendarBtn.addEventListener("click", openCalendarWindow);
}

if (closeCalendarWindow && calendarWindow) {
 closeCalendarWindow.addEventListener("click", function () {
 calendarWindow.style.display = "none";
 updateModalOverlay();
 });
}

if (notificationsStatus) {
 refreshNotificationsStatus();
}

const notificationsWidgetCheckbox = document.getElementById("notifications-widget");
const notificationsWindow = document.getElementById("notifications-window");
const closeNotificationsWindow = document.getElementById("close-notifications-window");
const openNotificationsBtn = document.getElementById("open-notifications-btn");

function openNotificationsWindow() {
 if (notificationsWindow) {
 notificationsWindow.style.display = "block";
 updateModalOverlay();
 }
}

if (notificationsWidgetCheckbox) {
 notificationsWidgetCheckbox.addEventListener("change", function () {
 if (notificationsWidgetCheckbox.checked) {
 openNotificationsWindow();
 }
 });
}

if (openNotificationsBtn) {
 openNotificationsBtn.addEventListener("click", openNotificationsWindow);
}

if (closeNotificationsWindow && notificationsWindow) {
 closeNotificationsWindow.addEventListener("click", function () {
 notificationsWindow.style.display = "none";
 updateModalOverlay();
 });
}

const stockCryptoWidgetCheckbox = document.getElementById("stock-crypto-widget");
const stockCryptoWindow = document.getElementById("stock-crypto-window");
const closeStockCryptoWindow = document.getElementById("close-stock-crypto-window");
const stockCryptoSearchInput = document.getElementById("stock-crypto-search");
const stockCryptoSuggestions = document.getElementById("stock-crypto-suggestions");
const stockCryptoSelectedBox = document.getElementById("stock-crypto-selected");
const stockCryptoSelectedLabel = document.getElementById("stock-crypto-selected-label");
const saveStockCryptoBtn = document.getElementById("save-stock-crypto");
const openStockCryptoBtn = document.getElementById("open-stock-crypto-btn");

function openStockCryptoWindow() {
 if (!stockCryptoWindow) return;
 stockCryptoWindow.style.display = "block";
 updateModalOverlay();
 if (stockCryptoSearchInput) stockCryptoSearchInput.focus();
}

if (stockCryptoWidgetCheckbox) {
 stockCryptoWidgetCheckbox.addEventListener("change", function () {
 if (stockCryptoWidgetCheckbox.checked) {
 openStockCryptoWindow();
 }
 });
}

if (openStockCryptoBtn) {
 openStockCryptoBtn.addEventListener("click", openStockCryptoWindow);
}

if (closeStockCryptoWindow && stockCryptoWindow) {
 closeStockCryptoWindow.addEventListener("click", function () {
 stockCryptoWindow.style.display = "none";
 updateModalOverlay();
 });
}

function renderStockCryptoSelection() {
 if (!stockCryptoSelectedBox || !stockCryptoSelectedLabel) return;
 if (stockCryptoSelection) {
 const typeLabel = stockCryptoSelection.type === "crypto" ? "Crypto" : "Stock";
 stockCryptoSelectedLabel.textContent = `${stockCryptoSelection.name} (${stockCryptoSelection.symbol}) — ${typeLabel}`;
 stockCryptoSelectedBox.style.display = "block";
 } else {
 stockCryptoSelectedBox.style.display = "none";
 }
}

let stockCryptoDebounceTimer;

if (stockCryptoSearchInput && stockCryptoSuggestions) {
 stockCryptoSearchInput.addEventListener("input", function () {
 clearTimeout(stockCryptoDebounceTimer);
 const query = stockCryptoSearchInput.value.trim();

 if (query.length < 1) {
 stockCryptoSuggestions.innerHTML = "";
 return;
 }

 stockCryptoDebounceTimer = setTimeout(async () => {
 try {
 const res = await fetch(`${API_BASE}/finance/search?q=${encodeURIComponent(query)}`);
 const data = await res.json();          stockCryptoSuggestions.innerHTML = "";
          const results = data.results || [];
          results.forEach(result => {
            const li = document.createElement("li");
            const typeLabel = result.type === "crypto" ? "Crypto" : "Stock";
            li.textContent = `${result.name} (${result.symbol})`;

            const typeSpan = document.createElement("span");
            typeSpan.className = "suggestion-type";
            typeSpan.textContent = typeLabel;
            li.appendChild(typeSpan);

            li.addEventListener("click", function () {
              stockCryptoSelection = {
                type: result.type,
                symbol: result.symbol,
                name: result.name,
                id: result.id,
              };
              renderStockCryptoSelection();
              stockCryptoSearchInput.value = "";
              stockCryptoSuggestions.innerHTML = "";
            });

            stockCryptoSuggestions.appendChild(li);
          });
          if (results.length === 0) {
            const li = document.createElement("li");
            li.className = "suggestion-empty";
            li.textContent = "No matches found. Check your spelling or try another name.";
            stockCryptoSuggestions.appendChild(li);
          }
 } catch (e) {
 stockCryptoSuggestions.innerHTML = "<li>Server not reachable.</li>";
 }
 }, 400);
 });
}

if (saveStockCryptoBtn && stockCryptoWindow) {
 saveStockCryptoBtn.addEventListener("click", function () {
 stockCryptoWindow.style.display = "none";
 updateModalOverlay();
 });
}

(function () {
 const startBtn = document.getElementById("start-btn");
 if (!startBtn) return;

 startBtn.addEventListener("click", async () => {
 const originalText = startBtn.textContent;
 startBtn.disabled = true;
 startBtn.textContent = "Starting...";

 try {
 const res = await fetch("/launch", { method: "POST" });
 const data = await res.json();

 if (res.ok && data.status === "ok") {
 showNotification("Dashboard started successfully!", "success");
 startBtn.textContent = "Dashboard is running";
 setTimeout(() => {
 startBtn.disabled = false;
 startBtn.textContent = originalText;
 }, 4000);
 } else {
 const msg = data.error || "Unknown error";
 showNotification("Error: " + msg, "error");
 startBtn.disabled = false;
 startBtn.textContent = originalText;
 }
 } catch (err) {
 showNotification("Server not reachable - is server.py running?", "error");
 startBtn.disabled = false;
 startBtn.textContent = originalText;
 }
 });
})();

const settingsTrigger = document.getElementById("settings-trigger");
const settingsMenu = document.getElementById("settings-menu");

if (settingsTrigger && settingsMenu) {
 settingsTrigger.addEventListener("click", function(e) {
 e.stopPropagation();
 settingsMenu.classList.toggle("open");
 });

 document.addEventListener("click", function(e) {
 if (!settingsMenu.contains(e.target)) {
 settingsMenu.classList.remove("open");
 }
 });
}

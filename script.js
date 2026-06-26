const API_BASE = window.location.protocol === "file:" ? "http://localhost:8000" : window.location.origin;

const connectBtn = document.getElementById('connect-google-calendar-btn');
const disconnectBtn = document.getElementById('disconnect-google-calendar-btn');
const calendarStatus = document.getElementById('calendar-connection-status');
const eventsList = document.getElementById('calendar-events-list');

// Holds the currently chosen stock/crypto suggestion until "Save" is pressed,
// or the value restored from settings.json on load.
// Shape: { type: "stock" | "crypto", symbol: "AAPL", name: "Apple Inc." }
let stockCryptoSelection = null;

if (connectBtn) {
    connectBtn.addEventListener('click', async () => {
        try {
            const res = await fetch(`${API_BASE}/auth/google`);
            const data = await res.json();
            if (!res.ok || !data.url) {
                showNotification(data.error ?? "Could not start Google login.", "error");
                return;
            }
            // Zur Google OAuth Seite weiterleiten
            window.location.href = data.url;
        } catch (e) {
            showNotification("Server not reachable.", "error");
        }
    });
}

if (disconnectBtn) {
    disconnectBtn.addEventListener('click', async () => {
        try {
            await fetch(`${API_BASE}/calendar/disconnect`, { method: "POST" });
            showNotification("Google Calendar disconnected.", "info");
            refreshCalendarStatus();
        } catch (e) {
            showNotification("Server not reachable.", "error");
        }
    });
}

async function refreshCalendarStatus() {
    if (!calendarStatus) return;
    try {
        const res = await fetch(`${API_BASE}/calendar/status`);
        const data = await res.json();

        if (data.connected) {
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
        calendarStatus.textContent = "Could not reach server.";
    }
}

async function loadCalendarEvents() {
    if (!eventsList) return;
    try {
        const res = await fetch(`${API_BASE}/calendar/events`);
        const data = await res.json();

        if (!res.ok) {
            eventsList.innerHTML = `<li>${data.error ?? "Could not load events."}</li>`;
            return;
        }

        eventsList.innerHTML = "";
        if (!data.events || data.events.length === 0) {
            eventsList.innerHTML = "<li>No upcoming events.</li>";
            return;
        }

        data.events.forEach(event => {
            const li = document.createElement("li");
            const start = event.start?.dateTime || event.start?.date || "";
            const startLabel = start ? new Date(start).toLocaleString() : "";
            li.textContent = `${startLabel} — ${event.summary ?? "(no title)"}`;
            eventsList.appendChild(li);
        });
    } catch (e) {
        eventsList.innerHTML = "<li>Server not reachable.</li>";
    }
}

// --- Notifications widget (Gmail) ---
// Uses the same Google login as the Calendar widget (/auth/google), just
// with the gmail.readonly scope added on the server side.

const connectMailBtn = document.getElementById('connect-google-mail-btn');
const disconnectMailBtn = document.getElementById('disconnect-google-mail-btn');
const notificationsStatus = document.getElementById('notifications-connection-status');
const messagesList = document.getElementById('notifications-messages-list');

if (connectMailBtn) {
    connectMailBtn.addEventListener('click', async () => {
        try {
            const res = await fetch(`${API_BASE}/auth/google`);
            const data = await res.json();
            if (!res.ok || !data.url) {
                showNotification(data.error ?? "Could not start Google login.", "error");
                return;
            }
            window.location.href = data.url;
        } catch (e) {
            showNotification("Server not reachable.", "error");
        }
    });
}

if (disconnectMailBtn) {
    disconnectMailBtn.addEventListener('click', async () => {
        try {
            await fetch(`${API_BASE}/calendar/disconnect`, { method: "POST" });
            showNotification("Google account disconnected.", "info");
            refreshNotificationsStatus();
        } catch (e) {
            showNotification("Server not reachable.", "error");
        }
    });
}

async function refreshNotificationsStatus() {
    if (!notificationsStatus) return;
    try {
        const res = await fetch(`${API_BASE}/calendar/status`);
        const data = await res.json();

        if (data.connected) {
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
        notificationsStatus.textContent = "Could not reach server.";
    }
}

async function loadMessages() {
    if (!messagesList) return;
    try {
        const res = await fetch(`${API_BASE}/notifications/messages`);
        const data = await res.json();

        if (!res.ok) {
            messagesList.innerHTML = `<li>${data.error ?? "Could not load messages."}</li>`;
            return;
        }

        messagesList.innerHTML = "";
        if (!data.messages || data.messages.length === 0) {
            messagesList.innerHTML = "<li>No messages found.</li>";
            return;
        }

        data.messages.forEach(message => {
            const li = document.createElement("li");

            const subject = document.createElement("span");
            subject.className = "message-subject";
            subject.textContent = message.subject;
            li.appendChild(subject);

            const from = document.createElement("span");
            from.className = "message-from";
            from.textContent = message.from;
            li.appendChild(from);

            const snippet = document.createElement("span");
            snippet.className = "message-snippet";
            snippet.textContent = message.snippet;
            li.appendChild(snippet);

            messagesList.appendChild(li);
        });
    } catch (e) {
        messagesList.innerHTML = "<li>Server not reachable.</li>";
    }
}

// Nach OAuth-Redirect zurück von Google: Status prüfen und Meldung anzeigen
function handleGoogleRedirectParams() {
    const params = new URLSearchParams(window.location.search);
    if (params.has("google_connected")) {
        showNotification("Google Calendar connected successfully.", "success");
        history.replaceState(null, "", window.location.pathname);
    } else if (params.has("google_error")) {
        showNotification("Google Calendar connection failed: " + params.get("google_error"), "error");
        history.replaceState(null, "", window.location.pathname);
    }
}

async function loadSettings() {
    try {
        const res = await fetch(`${API_BASE}/load`);
        if (!res.ok) return;
        const s = await res.json();

        if (s.location)      document.getElementById("location").value = s.location;
        if (s.useIpLocation) {
            document.getElementById("use-ip-location").checked = true;
            document.getElementById("location").disabled = true;
        }

        if (s.widgets) {
            for (const [key, value] of Object.entries(s.widgets)) {
                const map = {
                    weather: "weather-widget", notifications: "notifications-widget",
                    dateTime: "date-time-widget", countdown: "countdown-widget",
                    calendar: "calendar-widget", stockCrypto: "stock-crypto-widget"
                };
                if (map[key]) document.getElementById(map[key]).checked = value;
            }
            syncWidgetStars();
        }

        if (s.starredWidget) {
            const star = document.getElementById(s.starredWidget);
            if (star) star.checked = true;
        }

        if (s.theme)       document.getElementById("theme-select").value = s.theme;
        if (s.customColor) document.getElementById("custom-color").value = s.customColor;
        applyThemeCustomColorExclusivity();

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
    const res = await fetch(url, {
        headers: { "Accept-Language": "en" }
    });
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
    const dashboardSection = document.getElementById("dashboard");
    const settingsSection = document.getElementById("settings");
    const aboutSection = document.getElementById("About-me");

    if (homeSection) homeSection.style.display = sectionId === "home" ? "block" : "none";
    if (dashboardSection) dashboardSection.style.display = sectionId === "dashboard" ? "flex" : "none";
    if (settingsSection) settingsSection.style.display = sectionId === "settings" ? "block" : "none";
    if (aboutSection) aboutSection.style.display = sectionId === "about" ? "block" : "none";
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
const textfeld = document.getElementById("location");
if (checkbox && textfeld) {
    checkbox.addEventListener("change", function() {
        textfeld.disabled = checkbox.checked;
    });
}

const checkboxes = document.querySelectorAll('.limited-checkbox');

checkboxes.forEach(checkbox => {
    checkbox.addEventListener('change', () => {
        const checked = document.querySelectorAll('.limited-checkbox:checked');
        if (checked.length > 3) {
            checkbox.checked = false;
        }
    });
});

const widgetCheckboxes = document.querySelectorAll('#widgets-list .limited-checkbox');

function syncWidgetStars() {
    widgetCheckboxes.forEach(widgetCheckbox => {
        const widgetItem = widgetCheckbox.closest('li');
        const starButton = widgetItem ? widgetItem.querySelector('.star-checkbox') : null;

        if (!starButton) return;

        starButton.disabled = !widgetCheckbox.checked;

        if (!widgetCheckbox.checked) {
            starButton.checked = false;
        }
    });
}

widgetCheckboxes.forEach(widgetCheckbox => {
    widgetCheckbox.addEventListener('change', syncWidgetStars);
});

syncWidgetStars();
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

// Location Autocomplete
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

    document.addEventListener("click", function(e) {
        if (e.target !== locationInput) {
            suggestionsList.innerHTML = "";
        }
    });
}

const saveSettingsBtn = document.getElementById("save-settings-btn");

if (saveSettingsBtn) {
    saveSettingsBtn.addEventListener("click", async function() {

        const checked = document.querySelectorAll('.limited-checkbox:checked');
        const starred = document.querySelector('input[name="widget-star"]:checked');
        const location = document.getElementById("location").value;
        const useIp = document.getElementById("use-ip-location").checked;

        if (checked.length === 0) {
            showNotification("Please select at least one widget.", "error");
            return;
        }

        if (!starred) {
            showNotification("Please star at least one widget.", "error");
            return;
        }

        if (!useIp && location.trim() === "") {
            showNotification("Please enter a location or enable IP location.", "error");
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
    starredWidget: document.querySelector('input[name="widget-star"]:checked')?.id ?? null,
    theme: document.getElementById("theme-select").value,
    customColor: document.getElementById("custom-color").value,
    countdownDate: document.getElementById("countdown-date").value,
    stockCryptoSelection: stockCryptoSelection
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

// Intelligente Funktion: prüft ob noch ein Modal offen ist
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

// Alle EventListener anpassen um updateModalOverlay zu nutzen
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

// Checkbox: öffnet das Popup beim Aktivieren, leert das Datum beim Deaktivieren.
if (countdownWidget) {
    countdownWidget.addEventListener("change", function () {
        if (countdownWidget.checked) {
            openCountdownWindow();
        } else if (countdownDate) {
            countdownDate.value = "";
        }
    });
}

// "Configure"-Button öffnet das Popup ebenfalls.
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

// Checkbox öffnet das Popup beim Aktivieren.
if (calendarWidgetCheckbox) {
    calendarWidgetCheckbox.addEventListener("change", function () {
        if (calendarWidgetCheckbox.checked) {
            openCalendarWindow();
        }
    });
}

// "Configure"-Button öffnet das Popup ebenfalls.
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

// Checkbox öffnet das Popup beim Aktivieren.
if (notificationsWidgetCheckbox) {
    notificationsWidgetCheckbox.addEventListener("change", function () {
        if (notificationsWidgetCheckbox.checked) {
            openNotificationsWindow();
        }
    });
}

// "Configure"-Button öffnet das Popup ebenfalls.
if (openNotificationsBtn) {
    openNotificationsBtn.addEventListener("click", openNotificationsWindow);
}

if (closeNotificationsWindow && notificationsWindow) {
    closeNotificationsWindow.addEventListener("click", function () {
        notificationsWindow.style.display = "none";
        updateModalOverlay();
    });
}

// --- Stock / Crypto widget ---

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

// Checkbox öffnet das Popup beim Aktivieren.
if (stockCryptoWidgetCheckbox) {
    stockCryptoWidgetCheckbox.addEventListener("change", function () {
        if (stockCryptoWidgetCheckbox.checked) {
            openStockCryptoWindow();
        }
    });
}

// "Configure"-Button öffnet das Popup ebenfalls.
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
                const data = await res.json();

                stockCryptoSuggestions.innerHTML = "";
                (data.results || []).forEach(result => {
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
                        };
                        renderStockCryptoSelection();
                        stockCryptoSearchInput.value = "";
                        stockCryptoSuggestions.innerHTML = "";
                    });

                    stockCryptoSuggestions.appendChild(li);
                });
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

// --- Theme select / custom color: mutually exclusive ---

const themeSelect = document.getElementById("theme-select");
const customColorInput = document.getElementById("custom-color");

function applyThemeCustomColorExclusivity() {
    if (!themeSelect || !customColorInput) return;
    // Ein echtes Theme ist gewählt (nicht die leere "Choose an option")
    // -> Custom-Color-Picker deaktivieren.
    customColorInput.disabled = !!themeSelect.value;
}

if (themeSelect) {
    themeSelect.addEventListener("change", function () {
        applyThemeCustomColorExclusivity();
    });
}

if (customColorInput) {
    customColorInput.addEventListener("input", function () {
        // Sobald eine eigene Farbe gewählt wird, Theme-Auswahl zurücksetzen.
        if (themeSelect && themeSelect.value) {
            themeSelect.value = "";
            applyThemeCustomColorExclusivity();
        }
    });
}

// Zustand direkt beim Laden der Seite einmal anwenden (falls schon ein
// Theme aus settings.json gesetzt wurde, bevor der Nutzer etwas anklickt).
applyThemeCustomColorExclusivity();
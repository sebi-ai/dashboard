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

const countdownWidget = document.getElementById("countdown-widget");
const countdownWindow = document.getElementById("countdown-window");
const closeCountdown = document.getElementById("save-countdown");
const countdownDate = document.getElementById("countdown-date");

if (countdownWidget && countdownWindow) {
    countdownWidget.addEventListener("change", function () {
        if (countdownWidget.checked) {
            countdownWindow.style.display = "block";
            countdownDate.focus();
        } else {
            countdownWindow.style.display = "none";
            countdownDate.value = "";
        }
    });
}

if (countdownWidget && countdownWindow && closeCountdown && countdownDate) {
    countdownWidget.addEventListener("change", function () {
        if (countdownWidget.checked) {
            countdownWindow.style.display = "block";
            countdownDate.focus();
        } else {
            countdownWindow.style.display = "none";
            countdownDate.value = "";
        }
    });

    closeCountdown.addEventListener("click", function () {
        countdownWindow.style.display = "none";
    });
}

if (calendarStatus) {
    handleGoogleRedirectParams();
    refreshCalendarStatus();
}

const calendarWidgetCheckbox = document.getElementById("calendar-widget");
const calendarWindow = document.getElementById("calendar-window");
const closeCalendarWindow = document.getElementById("close-calendar-window");

if (calendarWidgetCheckbox && calendarWindow) {
    calendarWidgetCheckbox.addEventListener("change", function () {
        if (calendarWidgetCheckbox.checked) {
            calendarWindow.style.display = "block";
        } else {
            calendarWindow.style.display = "none";
        }
    });
}

if (closeCalendarWindow && calendarWindow) {
    closeCalendarWindow.addEventListener("click", function () {
        calendarWindow.style.display = "none";
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

if (stockCryptoWidgetCheckbox && stockCryptoWindow) {
    stockCryptoWidgetCheckbox.addEventListener("change", function () {
        if (stockCryptoWidgetCheckbox.checked) {
            stockCryptoWindow.style.display = "block";
            if (stockCryptoSearchInput) stockCryptoSearchInput.focus();
        } else {
            stockCryptoWindow.style.display = "none";
        }
    });
}

if (closeStockCryptoWindow && stockCryptoWindow) {
    closeStockCryptoWindow.addEventListener("click", function () {
        stockCryptoWindow.style.display = "none";
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
    });
}
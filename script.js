const API_BASE = window.location.protocol === "file:" ? "http://localhost:8000" : window.location.origin;

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
    document.getElementById("home").style.display = sectionId === "home" ? "block" : "none";
    document.getElementById("dashboard").style.display = sectionId === "dashboard" ? "flex" : "none";
    document.getElementById("settings").style.display = sectionId === "settings" ? "block" : "none";
    document.getElementById("About-me").style.display = sectionId === "about" ? "block" : "none";
}

document.getElementById("redirect-start-btn").addEventListener("click", function(e) {
    e.preventDefault();
    showSection("dashboard");
});

document.getElementById("home-btn").addEventListener("click", function(e) {
    e.preventDefault();
    showSection("home");
});

document.getElementById("settings-btn").addEventListener("click", function(e) {
    e.preventDefault();
    showSection("settings");
});

document.getElementById("about-btn").addEventListener("click", function(e) {
    e.preventDefault();
    showSection("about");
});

showSection("home");

const checkbox = document.getElementById("use-ip-location");
const textfeld = document.getElementById("location");
checkbox.addEventListener("change", function() {
    textfeld.disabled = checkbox.checked;
});

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
loadSettings();

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

document.getElementById("save-settings-btn").addEventListener("click", async function() {

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
        location:      location,
        coordinates:   coords,
        useIpLocation: useIp,

        widgets: {
            weather:       document.getElementById("weather-widget").checked,
            notifications: document.getElementById("notifications-widget").checked,
            dateTime:      document.getElementById("date-time-widget").checked,
            countdown:     document.getElementById("countdown-widget").checked,
            calendar:      document.getElementById("calendar-widget").checked,
            stockCrypto:   document.getElementById("stock-crypto-widget").checked,
        },

        starredWidget: document.querySelector('input[name="widget-star"]:checked')?.id ?? null,
        theme:         document.getElementById("theme-select").value,
        customColor:   document.getElementById("custom-color").value,
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

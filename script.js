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

    if (!starButton) {
      return;
    }

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

document.getElementById("save-settings-btn").addEventListener("click", async function() {
    const settings = {
        location:      document.getElementById("location").value,
        useIpLocation: document.getElementById("use-ip-location").checked,

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
        await fetch("http://localhost:8000/save", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(settings)
        });
        showAlert();
    } catch (error) {
        showAlert();
        console.error("Server nicht erreichbar:", error);
    }
});

function showAlert() {
    document.getElementById("settings-saved-alert").style.display = "block";

    setTimeout(closeAlert, 2500);
}

function closeAlert() {
    document.getElementById("settings-saved-alert").style.display = "none";
}
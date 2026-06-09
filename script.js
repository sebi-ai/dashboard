function showSection(sectionId) {
  document.getElementById("home").style.display = sectionId === "home" ? "block" : "none";
  document.getElementById("dashboard").style.display = sectionId === "dashboard" ? "flex" : "none";
  document.getElementById("settings").style.display = sectionId === "settings" ? "block" : "none";
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

showSection("home");
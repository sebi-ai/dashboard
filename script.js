function showSection(sectionId) {
  var sections = document.querySelectorAll("section");
  sections.forEach(function(section) {
    section.style.display = section.id === sectionId ? "block" : "none";
  });

  var targetSection = document.getElementById(sectionId);
  if (targetSection) {
    targetSection.scrollIntoView({ behavior: "smooth" });
  }
}

var homeBtn = document.getElementById("home-btn");
if (homeBtn) {
  homeBtn.addEventListener("click", function() {
    showSection("home");
  });
}

var openDashboardBtn = document.getElementById("redirect-start-btn");
if (openDashboardBtn) {
  openDashboardBtn.addEventListener("click", function() {
    showSection("dashboard");
  });
}

var settingsBtn = document.getElementById("settings-btn");
if (settingsBtn) {
  settingsBtn.addEventListener("click", function() {
    showSection("settings");
  });
}

document.getElementById("redirect-start-btn").addEventListener("click", function(e) {
  e.preventDefault();
  document.getElementById("home").style.display = "none";
  document.getElementById("dashboard").style.display = "flex";
});

document.getElementById("home-btn").addEventListener("click", function(e) {
  e.preventDefault();
  document.getElementById("home").style.display = "block";
  document.getElementById("dashboard").style.display = "none";
});
(function () {
  var t = "light";
  try { t = localStorage.getItem("slwb-theme") || "light"; } catch (e) {}
  document.documentElement.setAttribute("data-theme", t === "dark" ? "dark" : "light");
})();

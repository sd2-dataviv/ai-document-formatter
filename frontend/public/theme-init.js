// Applies the saved theme before first paint to avoid a light flash in dark mode.
// External (not inline) so it satisfies the production Content-Security-Policy.
(function () {
  var pref = "system";
  try {
    pref = localStorage.getItem("docformatter.theme") || "system";
  } catch (e) {}
  var dark = pref === "dark" || (pref !== "light" && window.matchMedia("(prefers-color-scheme: dark)").matches);
  if (dark) document.documentElement.classList.add("dark");
  document.documentElement.style.colorScheme = dark ? "dark" : "light";
})();

(function () {
  "use strict";

  // --- Mobiles Menü ---
  var navToggle = document.querySelector(".nav-toggle");
  var mainNav = document.querySelector(".main-nav");
  if (navToggle && mainNav) {
    navToggle.addEventListener("click", function () {
      var open = mainNav.classList.toggle("is-open");
      navToggle.setAttribute("aria-expanded", open ? "true" : "false");
      document.body.style.overflow = open ? "hidden" : "";
    });
    mainNav.querySelectorAll(".has-submenu > a").forEach(function (link) {
      link.addEventListener("click", function (e) {
        if (window.matchMedia("(max-width: 959px)").matches) {
          e.preventDefault();
          link.parentElement.classList.toggle("is-open");
        }
      });
    });
  }

  // --- Vorher/Nachher-Schieberegler ---
  document.querySelectorAll(".ba-slider").forEach(function (slider) {
    var range = slider.querySelector(".ba-range");
    if (!range) return;
    var update = function () {
      slider.style.setProperty("--ba-pos", range.value + "%");
    };
    range.addEventListener("input", update);
    update();
  });

  // --- Akkordeon (FAQ) ---
  document.querySelectorAll(".accordion-trigger").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var expanded = btn.getAttribute("aria-expanded") === "true";
      var panel = document.getElementById(btn.getAttribute("aria-controls"));
      btn.setAttribute("aria-expanded", expanded ? "false" : "true");
      if (panel) panel.setAttribute("data-open", expanded ? "false" : "true");
    });
  });
})();

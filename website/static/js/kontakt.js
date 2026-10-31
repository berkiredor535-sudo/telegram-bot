(function () {
  "use strict";
  var form = document.getElementById("kontakt-form");
  if (!form || !window.fetch || !window.FormData) return;

  var lastSubmit = 0;

  form.addEventListener("submit", function (e) {
    var now = Date.now();
    if (now - lastSubmit < 4000) {
      e.preventDefault();
      return;
    }
    lastSubmit = now;
    e.preventDefault();

    var submitBtn = form.querySelector("[type=submit]");
    var alertBox = document.getElementById("form-alert");
    submitBtn.disabled = true;
    submitBtn.textContent = "Wird gesendet …";

    fetch(form.action, {
      method: "POST",
      body: new FormData(form),
      headers: { "X-Requested-With": "XMLHttpRequest" },
    })
      .then(function (res) {
        if (res.ok) {
          window.location.href = "/danke";
          return;
        }
        return res.json().then(function (data) {
          throw new Error((data && data.message) || "Senden fehlgeschlagen.");
        });
      })
      .catch(function (err) {
        if (alertBox) {
          alertBox.textContent =
            err.message || "Es ist ein Fehler aufgetreten. Bitte versuchen Sie es erneut oder rufen Sie uns an.";
          alertBox.className = "form-alert error";
          alertBox.hidden = false;
          alertBox.scrollIntoView({ behavior: "smooth" });
        }
        submitBtn.disabled = false;
        submitBtn.textContent = "Nachricht senden";
      });
  });
})();

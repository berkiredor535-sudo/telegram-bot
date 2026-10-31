(function () {
  "use strict";

  var form = document.getElementById("schaden-form");
  if (!form) return;

  var steps = Array.prototype.slice.call(form.querySelectorAll(".form-step"));
  var dots = Array.prototype.slice.call(document.querySelectorAll(".stepper .dot-step"));
  var current = 0;
  var MAX_PHOTOS = 5;
  var MAX_PHOTO_MB = 8;
  var photos = [];

  function showStep(index) {
    steps.forEach(function (step, i) {
      step.hidden = i !== index;
    });
    dots.forEach(function (dot, i) {
      dot.classList.toggle("is-active", i === index);
      dot.classList.toggle("is-done", i < index);
    });
    form.querySelectorAll(".form-nav")[index] &&
      form.querySelectorAll(".form-nav")[index].scrollIntoView({ block: "nearest" });
    window.scrollTo({ top: form.offsetTop - 140, behavior: "smooth" });
  }

  function validateStep(index) {
    var step = steps[index];
    var fields = step.querySelectorAll("input, select, textarea");
    var valid = true;
    fields.forEach(function (field) {
      if (!field.checkValidity()) {
        field.reportValidity();
        valid = false;
      }
    });
    return valid;
  }

  form.querySelectorAll("[data-next]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      if (!validateStep(current)) return;
      if (current < steps.length - 1) {
        current += 1;
        showStep(current);
      }
    });
  });

  form.querySelectorAll("[data-prev]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      if (current > 0) {
        current -= 1;
        showStep(current);
      }
    });
  });

  showStep(0);

  // --- Fotoupload mit Vorschau & Mengenbegrenzung ---
  var dropzone = document.getElementById("dropzone");
  var fileInput = document.getElementById("photos-input");
  var preview = document.getElementById("photo-preview");
  var photoCount = document.getElementById("photo-count");
  var photoError = document.getElementById("photo-error");

  function renderPreview() {
    preview.innerHTML = "";
    photos.forEach(function (file, i) {
      var thumb = document.createElement("div");
      thumb.className = "thumb";
      var img = document.createElement("img");
      img.src = URL.createObjectURL(file);
      img.alt = "Foto " + (i + 1) + " des Schadens";
      var removeBtn = document.createElement("button");
      removeBtn.type = "button";
      removeBtn.setAttribute("aria-label", "Foto entfernen");
      removeBtn.textContent = "✕";
      removeBtn.addEventListener("click", function () {
        photos.splice(i, 1);
        renderPreview();
      });
      thumb.appendChild(img);
      thumb.appendChild(removeBtn);
      preview.appendChild(thumb);
    });
    photoCount.textContent = photos.length + " / " + MAX_PHOTOS + " Fotos";
  }

  function addFiles(fileList) {
    photoError.textContent = "";
    Array.prototype.forEach.call(fileList, function (file) {
      if (!/^image\//.test(file.type)) {
        photoError.textContent = "Nur Bilddateien sind erlaubt.";
        return;
      }
      if (file.size > MAX_PHOTO_MB * 1024 * 1024) {
        photoError.textContent = "Foto zu groß (max. " + MAX_PHOTO_MB + " MB).";
        return;
      }
      if (photos.length >= MAX_PHOTOS) {
        photoError.textContent = "Maximal " + MAX_PHOTOS + " Fotos möglich.";
        return;
      }
      photos.push(file);
    });
    renderPreview();
    syncFileInput();
  }

  function syncFileInput() {
    var dt = new DataTransfer();
    photos.forEach(function (file) { dt.items.add(file); });
    fileInput.files = dt.files;
  }

  if (dropzone && fileInput) {
    dropzone.addEventListener("click", function () { fileInput.click(); });
    dropzone.addEventListener("keydown", function (e) {
      if (e.key === "Enter" || e.key === " ") { e.preventDefault(); fileInput.click(); }
    });
    fileInput.addEventListener("change", function () { addFiles(fileInput.files); });
    ["dragenter", "dragover"].forEach(function (evt) {
      dropzone.addEventListener(evt, function (e) {
        e.preventDefault();
        dropzone.classList.add("is-dragover");
      });
    });
    ["dragleave", "drop"].forEach(function (evt) {
      dropzone.addEventListener(evt, function (e) {
        e.preventDefault();
        dropzone.classList.remove("is-dragover");
      });
    });
    dropzone.addEventListener("drop", function (e) {
      if (e.dataTransfer && e.dataTransfer.files) addFiles(e.dataTransfer.files);
    });
    renderPreview();
  }

  // --- Standort verwenden ---
  var locationBtn = document.getElementById("use-location");
  var locationStatus = document.getElementById("location-status");
  var latField = document.getElementById("field-lat");
  var lngField = document.getElementById("field-lng");

  if (locationBtn) {
    locationBtn.addEventListener("click", function () {
      if (!("geolocation" in navigator)) {
        locationStatus.textContent = "Standortfreigabe wird von diesem Browser nicht unterstützt.";
        locationStatus.className = "location-status is-error";
        return;
      }
      locationStatus.textContent = "Standort wird ermittelt …";
      locationStatus.className = "location-status";
      navigator.geolocation.getCurrentPosition(
        function (pos) {
          latField.value = pos.coords.latitude.toFixed(6);
          lngField.value = pos.coords.longitude.toFixed(6);
          locationStatus.textContent =
            "Standort erfasst (Genauigkeit ca. " + Math.round(pos.coords.accuracy) + " m). " +
            "Bitte ergänzen Sie trotzdem die Adresse unten, damit wir sicher hinfinden.";
          locationStatus.className = "location-status is-ok";
        },
        function () {
          locationStatus.textContent =
            "Standort konnte nicht ermittelt werden. Bitte tragen Sie die Adresse von Hand ein.";
          locationStatus.className = "location-status is-error";
        },
        { enableHighAccuracy: true, timeout: 10000 }
      );
    });
  }

  // --- Absenden per AJAX, mit Fallback auf normales POST ---
  var submitBtn = form.querySelector("[type=submit]");
  var lastSubmit = 0;

  form.addEventListener("submit", function (e) {
    if (!validateStep(steps.length - 1)) {
      e.preventDefault();
      return;
    }
    // einfache Clientseitige Drossel gegen Mehrfach-Klicks/Spam
    var now = Date.now();
    if (now - lastSubmit < 4000) {
      e.preventDefault();
      return;
    }
    lastSubmit = now;

    if (!window.fetch || !window.FormData) return; // normales POST als Fallback

    e.preventDefault();
    submitBtn.disabled = true;
    submitBtn.textContent = "Wird gesendet …";

    var formData = new FormData(form);
    fetch(form.action, {
      method: "POST",
      body: formData,
      headers: { "X-Requested-With": "XMLHttpRequest" },
    })
      .then(function (res) {
        if (res.redirected) {
          window.location.href = res.url;
          return;
        }
        if (res.ok) {
          window.location.href = "/danke";
        } else {
          return res.json().then(function (data) {
            throw new Error((data && data.message) || "Senden fehlgeschlagen.");
          });
        }
      })
      .catch(function (err) {
        var alertBox = document.getElementById("form-alert");
        if (alertBox) {
          alertBox.textContent = err.message || "Es ist ein Fehler aufgetreten. Bitte versuchen Sie es erneut oder rufen Sie uns an.";
          alertBox.className = "form-alert error";
          alertBox.hidden = false;
          alertBox.scrollIntoView({ behavior: "smooth" });
        }
        submitBtn.disabled = false;
        submitBtn.textContent = "Schaden melden";
      });
  });
})();

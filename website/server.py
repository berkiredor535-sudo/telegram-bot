"""
Webserver für die Firmenwebseite SR Ortung und Bautrocknung GbR.

Rendert die statischen Seiten (Jinja2-Templates) und verarbeitet die beiden
Formulare (Kontakt, Schaden melden). Eingehende Formulardaten werden
validiert, auf Spam geprüft (Honigtopf-Feld + Ratenbegrenzung je IP) und per
Telegram-Bot-API an die Geschäftsinhaber weitergeleitet. Es werden keine
API-Schlüssel im Browser ausgeliefert – Telegram-Token und Chat-ID bleiben
ausschließlich serverseitig in Umgebungsvariablen.

Umgebungsvariablen:
  TELEGRAM_BOT_TOKEN       Token des Telegram-Bots, der Benachrichtigungen
                           verschickt (optional – ohne Token werden
                           Anfragen nur lokal protokolliert/gespeichert).
  TELEGRAM_NOTIFY_CHAT_ID  Chat-ID, an die neue Anfragen gemeldet werden.
  PORT                     Port für den Entwicklungsserver (Standard 8000).

Start: python server.py
"""

from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
import uuid
from collections import defaultdict, deque
from pathlib import Path

from flask import Flask, jsonify, redirect, render_template, request, url_for

import requests

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
UPLOAD_DIR = DATA_DIR / "uploads"
SUBMISSIONS_LOG = DATA_DIR / "submissions.jsonl"

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_NOTIFY_CHAT_ID = os.environ.get("TELEGRAM_NOTIFY_CHAT_ID", "").strip()

HONEYPOT_FIELD = "firma_webseite"
MAX_PHOTOS = 5
MAX_PHOTO_BYTES = 8 * 1024 * 1024  # 8 MB pro Foto
ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/heic", "image/heif"}
RATE_LIMIT_WINDOW_SECONDS = 15 * 60
RATE_LIMIT_MAX_REQUESTS = 8

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("sr-ortung-website")

app = Flask(__name__, static_folder="static", template_folder="templates")
app.config["MAX_CONTENT_LENGTH"] = 40 * 1024 * 1024  # 40 MB Gesamtanfrage (Fotos)

SERVICES = {
    "leckageortung": {
        "title": "Leckageortung",
        "teaser": "Wir finden das Leck, bevor etwas aufgestemmt wird.",
    },
    "wasserschaden-bautrocknung": {
        "title": "Wasserschaden & Bautrocknung",
        "teaser": "Professionelle Trocknung mit lückenlosem Protokoll.",
    },
    "reparatur": {
        "title": "Reparatur",
        "teaser": "Undichte Leitung, defekte Verbindung, gerissenes Rohr – fachgerecht behoben.",
    },
    "wiederherstellung": {
        "title": "Wiederherstellung",
        "teaser": "Putz, Trockenbau, Estrich, Fliesen, Böden, Anstrich – alles aus einer Hand.",
    },
    "rohrreinigung": {
        "title": "Rohrreinigung",
        "teaser": "Toilette, Dusche, Küche, Grundleitung – auf Wunsch mit Kamera-Inspektion.",
    },
}

NAV_ITEMS = [
    {"label": "Startseite", "endpoint": "index"},
    {
        "label": "Leistungen",
        "endpoint": "leistungen_index",
        "children": [
            {"label": v["title"], "endpoint": "leistung_detail", "slug": k}
            for k, v in SERVICES.items()
        ],
    },
    {"label": "Versicherung", "endpoint": "versicherung"},
    {"label": "Über uns", "endpoint": "ueber_uns"},
    {"label": "Kontakt", "endpoint": "kontakt"},
]

_rate_limit_lock = threading.Lock()
_rate_limit_hits: dict[str, deque] = defaultdict(deque)

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _ensure_data_dirs() -> None:
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


def client_ip() -> str:
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.remote_addr or "unknown"


def rate_limited(bucket: str) -> bool:
    """Einfache gleitende Ratenbegrenzung je IP und Formular (Spam-Schutz)."""
    key = f"{bucket}:{client_ip()}"
    now = time.monotonic()
    with _rate_limit_lock:
        hits = _rate_limit_hits[key]
        while hits and now - hits[0] > RATE_LIMIT_WINDOW_SECONDS:
            hits.popleft()
        if len(hits) >= RATE_LIMIT_MAX_REQUESTS:
            return True
        hits.append(now)
        return False


def wants_json() -> bool:
    return request.headers.get("X-Requested-With") == "XMLHttpRequest"


def is_honeypot_filled(form) -> bool:
    return bool(form.get(HONEYPOT_FIELD, "").strip())


def clean(value: str | None, max_len: int = 500) -> str:
    return str(value or "").strip()[:max_len]


def notify_telegram(text: str, photo_paths: list[Path] | None = None) -> None:
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_NOTIFY_CHAT_ID:
        logger.info("Telegram nicht konfiguriert – Anfrage nur lokal gespeichert.\n%s", text)
        return
    api = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"
    try:
        requests.post(
            f"{api}/sendMessage",
            data={"chat_id": TELEGRAM_NOTIFY_CHAT_ID, "text": text},
            timeout=10,
        )
        for path in (photo_paths or [])[:MAX_PHOTOS]:
            with open(path, "rb") as fh:
                requests.post(
                    f"{api}/sendPhoto",
                    data={"chat_id": TELEGRAM_NOTIFY_CHAT_ID},
                    files={"photo": (path.name, fh)},
                    timeout=20,
                )
    except requests.RequestException:
        logger.exception("Telegram-Benachrichtigung fehlgeschlagen.")


def store_submission(kind: str, payload: dict) -> None:
    _ensure_data_dirs()
    record = {"kind": kind, "received_at": time.time(), **payload}
    try:
        with open(SUBMISSIONS_LOG, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError:
        logger.exception("Konnte Anfrage nicht lokal speichern.")


@app.context_processor
def inject_globals():
    return {
        "nav_items": NAV_ITEMS,
        "services": SERVICES,
        "current_path": request.path,
        "current_year": time.strftime("%Y"),
    }


# ---------------------------------------------------------------------------
# Statische Seiten
# ---------------------------------------------------------------------------

@app.get("/")
def index():
    return render_template("index.html", page_title="SR Ortung und Bautrocknung – Leckageortung & Bautrocknung in Grevenbroich")


@app.get("/leistungen/")
def leistungen_index():
    return render_template("leistungen/index.html", page_title="Leistungen – SR Ortung und Bautrocknung")


@app.get("/leistungen/<slug>")
def leistung_detail(slug):
    if slug not in SERVICES:
        return render_template("404.html"), 404
    template_map = {
        "leckageortung": "leistungen/leckageortung.html",
        "wasserschaden-bautrocknung": "leistungen/wasserschaden-bautrocknung.html",
        "reparatur": "leistungen/reparatur.html",
        "wiederherstellung": "leistungen/wiederherstellung.html",
        "rohrreinigung": "leistungen/rohrreinigung.html",
    }
    title = SERVICES[slug]["title"]
    return render_template(template_map[slug], page_title=f"{title} – SR Ortung und Bautrocknung", slug=slug)


@app.get("/versicherung")
def versicherung():
    return render_template("versicherung.html", page_title="Versicherung & Sofort-Tipps bei Wasserschaden")


@app.get("/ueber-uns")
def ueber_uns():
    return render_template("ueber-uns.html", page_title="Über uns – SR Ortung und Bautrocknung GbR")


@app.get("/danke")
def danke():
    return render_template("danke.html", page_title="Danke für Ihre Nachricht")


@app.get("/impressum")
def impressum():
    return render_template("impressum.html", page_title="Impressum")


@app.get("/datenschutz")
def datenschutz():
    return render_template("datenschutz.html", page_title="Datenschutzerklärung")


@app.get("/robots.txt")
def robots():
    return app.send_static_file("robots.txt")


@app.get("/sitemap.xml")
def sitemap():
    return app.send_static_file("sitemap.xml")


@app.errorhandler(404)
def not_found(_e):
    return render_template("404.html", page_title="Seite nicht gefunden"), 404


@app.errorhandler(413)
def too_large(_e):
    if wants_json():
        return jsonify(ok=False, message="Die Anfrage ist zu groß. Bitte weniger oder kleinere Fotos hochladen."), 413
    return render_template(
        "schaden-melden.html",
        page_title="Schaden melden",
        error="Die Anfrage ist zu groß. Bitte weniger oder kleinere Fotos hochladen (max. 5 Fotos, je max. 8 MB).",
    ), 413


# ---------------------------------------------------------------------------
# Kontaktformular
# ---------------------------------------------------------------------------

@app.route("/kontakt", methods=["GET", "POST"])
def kontakt():
    if request.method == "GET":
        return render_template("kontakt.html", page_title="Kontakt – Rückruf & Termin vereinbaren")

    form = request.form

    if is_honeypot_filled(form):
        # Spam still verwerfen, Absender aber nicht erkennen lassen.
        return redirect(url_for("danke")) if not wants_json() else jsonify(ok=True)

    if rate_limited("kontakt"):
        message = "Zu viele Anfragen von Ihrer Verbindung. Bitte versuchen Sie es später erneut oder rufen Sie uns an."
        if wants_json():
            return jsonify(ok=False, message=message), 429
        return render_template("kontakt.html", page_title="Kontakt – Rückruf & Termin vereinbaren", error=message, values=form), 429

    name = clean(form.get("name"), 120)
    telefon = clean(form.get("telefon"), 40)
    email = clean(form.get("email"), 160)
    anliegen = clean(form.get("anliegen"), 60)
    wunschtermin = clean(form.get("wunschtermin"), 60)
    nachricht = clean(form.get("nachricht"), 3000)
    datenschutz_ok = form.get("datenschutz") in ("on", "true", "1")

    errors = []
    if not name:
        errors.append("Bitte geben Sie Ihren Namen an.")
    if not telefon:
        errors.append("Bitte geben Sie eine Telefonnummer an.")
    if email and not EMAIL_RE.match(email):
        errors.append("Bitte geben Sie eine gültige E-Mail-Adresse an.")
    if not datenschutz_ok:
        errors.append("Bitte stimmen Sie der Datenschutzerklärung zu.")

    if errors:
        message = " ".join(errors)
        if wants_json():
            return jsonify(ok=False, message=message), 400
        return render_template("kontakt.html", page_title="Kontakt – Rückruf & Termin vereinbaren", error=message, values=form), 400

    text = (
        "\U0001F4DE Neue Kontaktanfrage (sr-ortung.de)\n"
        f"Anliegen: {anliegen or 'nicht angegeben'}\n"
        f"Name: {name}\n"
        f"Telefon: {telefon}\n"
        f"E-Mail: {email or '–'}\n"
        f"Wunschtermin: {wunschtermin or '–'}\n"
        f"Nachricht: {nachricht or '–'}"
    )
    store_submission("kontakt", {
        "name": name, "telefon": telefon, "email": email,
        "anliegen": anliegen, "wunschtermin": wunschtermin, "nachricht": nachricht,
    })
    notify_telegram(text)

    if wants_json():
        return jsonify(ok=True)
    return redirect(url_for("danke"))


# ---------------------------------------------------------------------------
# Schaden melden (mehrstufig)
# ---------------------------------------------------------------------------

SCHADENARTEN = {
    "wasserschaden": "Wasserschaden",
    "leckage": "Verdacht auf Leckage",
    "rohrverstopfung": "Rohrverstopfung",
    "sonstiges": "Sonstiges",
}


def _sniff_image_extension(header: bytes) -> str | None:
    """Bestimmt den Bildtyp anhand der echten Datei-Bytes (nicht des vom Client
    gesendeten Content-Type, der beliebig gefälscht werden kann)."""
    if header.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if header.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if header[:4] == b"RIFF" and header[8:12] == b"WEBP":
        return "webp"
    if header[4:12] in (b"ftypheic", b"ftypheix", b"ftypheim", b"ftypheis", b"ftypmif1"):
        return "heic"
    return None


def _save_photos(files) -> list[Path]:
    saved: list[Path] = []
    valid_files = [f for f in files if f and f.filename][:MAX_PHOTOS]
    if not valid_files:
        return saved
    _ensure_data_dirs()
    folder = UPLOAD_DIR / (time.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:8])
    folder.mkdir(parents=True, exist_ok=True)
    for idx, file in enumerate(valid_files, start=1):
        if file.mimetype not in ALLOWED_IMAGE_TYPES:
            continue
        file.stream.seek(0, os.SEEK_END)
        size = file.stream.tell()
        file.stream.seek(0)
        if size > MAX_PHOTO_BYTES or size == 0:
            continue
        header = file.stream.read(16)
        file.stream.seek(0)
        ext = _sniff_image_extension(header)
        if ext is None:
            continue
        # Fester, aus den Datei-Bytes abgeleiteter Dateiname – der vom Client
        # gesendete Name/​Endung wird nie übernommen, damit kein ausführbarer
        # Dateityp (z. B. .html/.svg) mit gefälschtem Content-Type landen kann.
        dest = folder / f"{idx:02d}-foto.{ext}"
        file.save(dest)
        saved.append(dest)
    return saved


@app.route("/schaden-melden", methods=["GET", "POST"])
def schaden_melden():
    if request.method == "GET":
        return render_template(
            "schaden-melden.html",
            page_title="Schaden melden",
            schadenarten=SCHADENARTEN,
        )

    form = request.form

    if is_honeypot_filled(form):
        return redirect(url_for("danke")) if not wants_json() else jsonify(ok=True)

    if rate_limited("schaden-melden"):
        message = "Zu viele Anfragen von Ihrer Verbindung. Bitte versuchen Sie es später erneut oder rufen Sie uns direkt an."
        if wants_json():
            return jsonify(ok=False, message=message), 429
        return render_template("schaden-melden.html", page_title="Schaden melden", schadenarten=SCHADENARTEN, error=message, values=form), 429

    schadenart = clean(form.get("schadenart"), 40)
    name = clean(form.get("name"), 120)
    telefon = clean(form.get("telefon"), 40)
    email = clean(form.get("email"), 160)
    adresse = clean(form.get("adresse"), 300)
    lat = clean(form.get("lat"), 30)
    lng = clean(form.get("lng"), 30)
    versicherung_name = clean(form.get("versicherung"), 160)
    schadennummer = clean(form.get("schadennummer"), 80)
    wunschtermin = clean(form.get("wunschtermin"), 60)
    nachricht = clean(form.get("nachricht"), 3000)
    datenschutz_ok = form.get("datenschutz") in ("on", "true", "1")

    errors = []
    if schadenart not in SCHADENARTEN:
        errors.append("Bitte wählen Sie die Art des Schadens.")
    if not name:
        errors.append("Bitte geben Sie Ihren Namen an.")
    if not telefon:
        errors.append("Bitte geben Sie eine Telefonnummer an.")
    if email and not EMAIL_RE.match(email):
        errors.append("Bitte geben Sie eine gültige E-Mail-Adresse an.")
    if not adresse:
        errors.append("Bitte geben Sie den Schadenort an.")
    if not datenschutz_ok:
        errors.append("Bitte stimmen Sie der Datenschutzerklärung zu.")

    if errors:
        message = " ".join(errors)
        if wants_json():
            return jsonify(ok=False, message=message), 400
        return render_template("schaden-melden.html", page_title="Schaden melden", schadenarten=SCHADENARTEN, error=message, values=form), 400

    uploaded = request.files.getlist("fotos")
    if len(uploaded) > MAX_PHOTOS:
        message = f"Es sind maximal {MAX_PHOTOS} Fotos erlaubt."
        if wants_json():
            return jsonify(ok=False, message=message), 400
        return render_template("schaden-melden.html", page_title="Schaden melden", schadenarten=SCHADENARTEN, error=message, values=form), 400
    saved_photos = _save_photos(uploaded)

    standort = f"{lat}, {lng}" if lat and lng else "nicht übermittelt"
    text = (
        "\U0001F6A8 Neue Schadenmeldung (sr-ortung.de)\n"
        f"Art: {SCHADENARTEN.get(schadenart, schadenart)}\n"
        f"Name: {name}\n"
        f"Telefon: {telefon}\n"
        f"E-Mail: {email or '–'}\n"
        f"Schadenort: {adresse}\n"
        f"GPS-Koordinaten: {standort}\n"
        f"Versicherung: {versicherung_name or '–'}\n"
        f"Schadennummer: {schadennummer or '–'}\n"
        f"Wunschtermin: {wunschtermin or '–'}\n"
        f"Nachricht: {nachricht or '–'}\n"
        f"Fotos: {len(saved_photos)}"
    )
    store_submission("schaden-melden", {
        "schadenart": schadenart, "name": name, "telefon": telefon, "email": email,
        "adresse": adresse, "lat": lat, "lng": lng, "versicherung": versicherung_name,
        "schadennummer": schadennummer, "wunschtermin": wunschtermin, "nachricht": nachricht,
        "fotos": [str(p.relative_to(DATA_DIR)) for p in saved_photos],
    })
    notify_telegram(text, saved_photos)

    if wants_json():
        return jsonify(ok=True)
    return redirect(url_for("danke"))


if __name__ == "__main__":
    _ensure_data_dirs()
    port = int(os.environ.get("PORT", "8000"))
    app.run(host="0.0.0.0", port=port, debug=False)

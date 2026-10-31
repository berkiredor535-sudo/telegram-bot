# SR Ortung und Bautrocknung – Webseite

Mehrseitige, mobil-optimierte Webseite (Flask + Jinja2-Templates, kein Build-Schritt,
kein Frontend-Framework) für die Firma **SR Ortung und Bautrocknung GbR**.

## Starten

```bash
cd website
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python server.py
```

Die Seite läuft dann auf <http://localhost:8000>.

## Umgebungsvariablen (optional)

Ohne diese Variablen funktioniert die Seite inklusive beider Formulare ganz normal –
eingehende Anfragen werden dann nur lokal protokolliert (`website/data/submissions.jsonl`)
und nicht per Telegram weitergeleitet.

| Variable | Zweck |
|---|---|
| `TELEGRAM_BOT_TOKEN` | Token des Telegram-Bots, der neue Kontakt- und Schadenanfragen an die Geschäftsinhaber weiterleitet. **Niemals im Browser-Code, nur serverseitig.** |
| `TELEGRAM_NOTIFY_CHAT_ID` | Chat-ID (Person oder Gruppe), an die Benachrichtigungen gesendet werden. |
| `PORT` | Port des Entwicklungsservers (Standard: `8000`). |

## Struktur

```
website/
  server.py            Flask-App: Routen, Formularverarbeitung, Spam-Schutz, Telegram-Weiterleitung
  templates/           Jinja2-Templates (base.html + Seiten + partials/)
  static/              CSS, JS, robots.txt, sitemap.xml, favicon.svg
  data/                (nicht versioniert) Formular-Eingänge & hochgeladene Schadenfotos
```

## Formulare & Spam-Schutz

- **Kontaktformular** (`/kontakt`) und **Schaden melden** (`/schaden-melden`, 4 Schritte)
  funktionieren auch ohne JavaScript (progressive enhancement: normales POST, Server
  rendert bei Fehlern dieselbe Seite mit Fehlermeldung neu, bei Erfolg Redirect auf `/danke`).
- Spam-Schutz: unsichtbares Honigtopf-Feld (`firma_webseite`) + serverseitige Ratenbegrenzung
  pro IP-Adresse und Formular.
- Hochgeladene Fotos (max. 5, je max. 8 MB, nur Bildformate) werden serverseitig geprüft und
  mit `secure_filename` gespeichert.

## Produktion

Der eingebaute Entwicklungsserver (`python server.py`) ist **nicht** für den produktiven
Betrieb gedacht. Für Produktion einen WSGI-Server verwenden, z. B.:

```bash
gunicorn --chdir website --bind 0.0.0.0:8000 server:app
```

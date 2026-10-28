# Telegram-Bot mit Claude

Der Bot beantwortet Nachrichten mit Claude und unterstützt /start, /help,
/reset und /remind <Minuten> <Text>.

## Lokal starten

Getestete Python-Version: 3.12. Die Typannotationen benötigen mindestens Python 3.10.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Vor dem Start müssen diese beiden Umgebungsvariablen gesetzt sein:

| Variable | Inhalt |
| --- | --- |
| TELEGRAM_BOT_TOKEN | Bot-Token von Telegram BotFather |
| ANTHROPIC_API_KEY | API-Schlüssel für Anthropic mit Zugriff auf das konfigurierte Modell |

Schlüssel über die Umgebungsvariablen bzw. die Secret-Verwaltung des Hosts
bereitstellen. Keine echten Schlüssel in Dateien oder Git eintragen.
Eine .env-Datei wird vom Bot nicht automatisch geladen.

```bash
python bot.py
```

Ohne erforderliche Variablen beendet sich der Bot mit einer verständlichen
Fehlermeldung. Das Modell ist in bot.py als claude-sonnet-4-6 konfiguriert;
der API-Zugang muss dieses Modell unterstützen.

## Deployment als Worker

Der Bot nutzt Telegram Long Polling und betreibt keinen HTTP-Server.
Als dauerhaft laufenden **Worker / Hintergrundprozess** bereitstellen.

- Build-Befehl: `python -m pip install -r requirements.txt`
- Startbefehl: `python bot.py`
- Python 3.12 in der Host-Konfiguration auswählen.
- Beide oben genannten Variablen in der Secret-Verwaltung des Hosts setzen.
- Genau eine Instanz pro Telegram-Bot-Token betreiben.

Das Procfile enthält:

```text
worker: python bot.py
```

Auf Plattformen mit Procfile-Unterstützung den Worker aktivieren bzw. auf
eine Instanz skalieren. Andere Hosts müssen den Startbefehl explizit bekommen.
Ein Web-Service mit verpflichtender Port-Prüfung passt zu diesem Polling-Bot
nicht. Der Host benötigt ausgehenden HTTPS-Zugriff auf Telegram und Anthropic.

## Behobene Startprobleme

- Ein leeres Procfile definiert keinen Startprozess.
- anthropic==0.39.0 verwendet intern das Argument `proxies`. httpx ab 0.28
  hat es entfernt; ohne zusätzliche Versionsbindung konnte eine frische
  Installation mit `TypeError: Client.__init__() got an unexpected keyword
  argument 'proxies'` abbrechen. requirements.txt bindet daher httpx==0.27.2.
- Der Anthropic-Client wird erst nach der Prüfung beider Umgebungsvariablen
  erstellt, damit fehlende Konfiguration klar gemeldet wird.
- Das Extra `[job-queue]` wird für /remind benötigt und bleibt enthalten.

## Prüfung nach dem Deployment

1. Worker-Logs auf Startfehler prüfen.
2. In Telegram /start senden.
3. Eine kurze Nachricht senden, um den Anthropic-Zugang zu prüfen.
4. Mit /remind 1 Test eine Erinnerung prüfen.

Gesprächsverlauf und Erinnerungen liegen nur im Arbeitsspeicher und gehen
bei Neustarts oder Deployments verloren. Für einen vollständigen Live-Test
sind gültige Zugangsdaten erforderlich; die lokalen Startprüfungen benötigen
keine echten Schlüssel und ersetzen diesen Live-Test nicht.

Offline-Startprüfungen nach der Installation: `python -m unittest -v test_startup.py`.

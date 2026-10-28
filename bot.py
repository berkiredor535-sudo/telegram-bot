"""
Telegram-Bot mit Claude (Anthropic API) als Chat-Assistent.

Funktionen:
- Beantwortet Fragen über Claude
- Merkt sich den Gesprächsverlauf pro Nutzer (im Arbeitsspeicher)
- /start, /reset, /help Befehle
- Erinnerungsfunktion: /remind <Minuten> <Text>

Setup siehe README.md
"""

import os
import logging
import asyncio
from datetime import datetime, timedelta

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)
from anthropic import Anthropic

# --- Konfiguration ---
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
MODEL = "claude-sonnet-4-6"
MAX_HISTORY_MESSAGES = 20  # wie viele Nachrichten im Gedächtnis behalten werden

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

client: Anthropic | None = None

# Gesprächsverlauf pro Chat-ID (nur im Arbeitsspeicher, geht bei Neustart verloren)
conversation_history: dict[int, list[dict]] = {}


# --- Hilfsfunktionen ---
def get_history(chat_id: int) -> list[dict]:
    return conversation_history.setdefault(chat_id, [])


def add_to_history(chat_id: int, role: str, content: str) -> None:
    history = get_history(chat_id)
    history.append({"role": role, "content": content})
    # History begrenzen, damit die Anfragen nicht zu groß werden
    if len(history) > MAX_HISTORY_MESSAGES:
        conversation_history[chat_id] = history[-MAX_HISTORY_MESSAGES:]


def ask_claude(chat_id: int, user_message: str) -> str:
    add_to_history(chat_id, "user", user_message)
    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=1024,
            system=(
                "Du bist ein hilfreicher, freundlicher Assistent in einem "
                "Telegram-Chat. Antworte knapp und klar, außer der Nutzer "
                "bittet um eine ausführliche Antwort."
            ),
            messages=get_history(chat_id),
        )
        reply_text = "".join(
            block.text for block in response.content if block.type == "text"
        )
    except Exception as e:
        logger.exception("Fehler bei Anthropic-API-Aufruf")
        return f"Entschuldigung, es gab einen Fehler bei der Anfrage: {e}"

    add_to_history(chat_id, "assistant", reply_text)
    return reply_text


# --- Telegram-Handler ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Hallo! Ich bin dein Assistent-Bot 🤖\n\n"
        "Schreib mir einfach eine Nachricht, und ich antworte dir.\n\n"
        "Befehle:\n"
        "/reset – Gespräch zurücksetzen\n"
        "/remind <Minuten> <Text> – Erinnerung setzen\n"
        "/help – Hilfe anzeigen"
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Ich kann:\n"
        "• Fragen beantworten und Gespräche führen\n"
        "• Mir den Kontext unseres Chats merken (/reset zum Zurücksetzen)\n"
        "• Erinnerungen setzen: /remind 10 Wasser trinken\n\n"
        "Schreib einfach drauf los!"
    )


async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    conversation_history[chat_id] = []
    await update.message.reply_text("Gesprächsverlauf wurde zurückgesetzt. ✅")


async def remind(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    args = context.args
    if len(args) < 2 or not args[0].isdigit():
        await update.message.reply_text(
            "Nutzung: /remind <Minuten> <Text>\nBeispiel: /remind 15 Pause machen"
        )
        return

    minutes = int(args[0])
    text = " ".join(args[1:])
    await update.message.reply_text(
        f"Ok, ich erinnere dich in {minutes} Minute(n) an: „{text}“ ⏰"
    )

    context.job_queue.run_once(
        send_reminder,
        when=timedelta(minutes=minutes),
        chat_id=chat_id,
        data=text,
    )


async def send_reminder(context: ContextTypes.DEFAULT_TYPE) -> None:
    job = context.job
    await context.bot.send_message(chat_id=job.chat_id, text=f"⏰ Erinnerung: {job.data}")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    user_message = update.message.text

    # "tippt..." Anzeige, während Claude antwortet
    await context.bot.send_chat_action(chat_id=chat_id, action="typing")

    loop = asyncio.get_event_loop()
    reply = await loop.run_in_executor(None, ask_claude, chat_id, user_message)

    await update.message.reply_text(reply)


def main() -> None:
    global client

    if not TELEGRAM_TOKEN:
        raise RuntimeError("Umgebungsvariable TELEGRAM_BOT_TOKEN fehlt.")
    if not ANTHROPIC_API_KEY:
        raise RuntimeError("Umgebungsvariable ANTHROPIC_API_KEY fehlt.")

    # Erst nach der Prüfung der Konfiguration einen API-Client erstellen.
    client = Anthropic(api_key=ANTHROPIC_API_KEY)
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("reset", reset))
    app.add_handler(CommandHandler("remind", remind))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("Bot gestartet ...")
    app.run_polling()


if __name__ == "__main__":
    main()

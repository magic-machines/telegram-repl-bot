import os
import httpx
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

load_dotenv()

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
REPL_URL = os.getenv("REPL_URL", "http://localhost:8000")

last_photo: dict[int, str] = {}
last_audio: dict[int, str] = {}


async def hello(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    async with httpx.AsyncClient(timeout=5) as client:
        try:
            response = await client.get(f"{REPL_URL}/health")
            data = response.json()
            status = data.get("status", "unknown")
            await update.message.reply_text(f"REPL service is up. Status: {status}")
        except Exception as e:
            await update.message.reply_text(f"REPL service is unreachable: {e}")


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    photo = update.message.photo[-1]  # largest available size
    file = await context.bot.get_file(photo.file_id)
    photo_bytes = await file.download_as_bytearray()

    async with httpx.AsyncClient(timeout=30) as client:
        try:
            response = await client.post(
                f"{REPL_URL}/photos/upload",
                files={"file": (f"{photo.file_id}.jpg", bytes(photo_bytes), "image/jpeg")},
            )
            data = response.json()
            photo_id = data.get("photo_id", "unknown")
            last_photo[update.message.from_user.id] = photo_id
            await update.message.reply_text(
                f"Photo uploaded. ID: {photo_id}\n\nUse /ocr to extract text from this photo."
            )
        except Exception as e:
            await update.message.reply_text(f"Failed to upload photo: {e}")


async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    file = await context.bot.get_file(update.message.voice.file_id)
    audio_bytes = await file.download_as_bytearray()

    async with httpx.AsyncClient(timeout=30) as client:
        try:
            response = await client.post(
                f"{REPL_URL}/audio/upload",
                files={"file": (f"{update.message.voice.file_id}.ogg", bytes(audio_bytes), "audio/ogg")},
            )
            data = response.json()
            audio_id = data.get("audio_id", "unknown")
            last_audio[update.message.from_user.id] = audio_id
            await update.message.reply_text(
                f"Voice message uploaded. ID: {audio_id}\n\nUse /transcribe to transcribe it."
            )
        except Exception as e:
            await update.message.reply_text(f"Failed to upload voice message: {e}")


async def transcribe(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    audio_id = last_audio.get(update.message.from_user.id)
    if not audio_id:
        await update.message.reply_text("No voice message uploaded yet. Send a voice message first.")
        return

    async with httpx.AsyncClient(timeout=120) as client:
        try:
            response = await client.get(f"{REPL_URL}/audio/{audio_id}/transcribe")
            data = response.json()
            text = data.get("text", "").strip()
            await update.message.reply_text(text if text else "No speech detected.")
        except Exception as e:
            await update.message.reply_text(f"Transcription failed: {e}")


async def ocr(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    photo_id = last_photo.get(update.message.from_user.id)
    if not photo_id:
        await update.message.reply_text("No photo uploaded yet. Send a photo first.")
        return

    async with httpx.AsyncClient(timeout=30) as client:
        try:
            response = await client.get(f"{REPL_URL}/photos/{photo_id}/analyse/ocr")
            data = response.json()
            text = data.get("text", "").strip()
            await update.message.reply_text(text if text else "No text found in the image.")
        except Exception as e:
            await update.message.reply_text(f"OCR failed: {e}")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Hello! Available commands:\n\n"
        "/hello — check if the REPL service is up\n"
        "/ocr — extract text from your last uploaded photo\n"
        "/transcribe — transcribe your last voice message\n"
        "/help — show detailed usage instructions\n"
        "/start — show this message"
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Here's how to use this bot:\n\n"
        "📷 *Photo OCR*\n"
        "1. Send a photo to the bot\n"
        "2. Use /ocr to extract text from it\n\n"
        "🎤 *Audio Transcription*\n"
        "1. Send a voice message to the bot\n"
        "2. Use /transcribe to get the transcription\n\n"
        "🔧 *Other Commands*\n"
        "/hello — check if the backend service is reachable\n"
        "/start — show the command list\n"
        "/help — show this help message\n\n"
        "Note: Only your most recently uploaded photo or voice message is stored per session.",
        parse_mode="Markdown",
    )


def main() -> None:
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("hello", hello))
    app.add_handler(CommandHandler("ocr", ocr))
    app.add_handler(CommandHandler("transcribe", transcribe))
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    print("Bot is running. Press Ctrl+C to stop.")
    app.run_polling()


if __name__ == "__main__":
    main()

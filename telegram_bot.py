from __future__ import annotations

import os
from dataclasses import dataclass
from typing import TypeVar, Generic, Callable, Awaitable

import httpx
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
)

load_dotenv()


# ---------------------------------------------------------------------------
# Type machinery
# ---------------------------------------------------------------------------

A = TypeVar("A")
E = TypeVar("E")


@dataclass(frozen=True)
class Ok(Generic[A]):
    value: A


@dataclass(frozen=True)
class Err(Generic[E]):
    error: E


# ---------------------------------------------------------------------------
# Domain types
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class BotConfig:
    token: str
    repl_url: str


@dataclass(frozen=True)
class SessionState:
    """Holds mutable session dicts at the I/O boundary.

    The dataclass is frozen (no rebinding of attributes); the dicts it
    carries are mutated at the outermost application layer — bot handlers —
    which is the only place where side effects are permitted.
    """
    last_photo: dict[int, str]
    last_audio: dict[int, str]


@dataclass(frozen=True)
class HealthStatus:
    status: str


@dataclass(frozen=True)
class PhotoUpload:
    photo_id: str


@dataclass(frozen=True)
class AudioUpload:
    audio_id: str


@dataclass(frozen=True)
class OcrResult:
    text: str


@dataclass(frozen=True)
class TranscriptionResult:
    text: str


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

def _load_config() -> BotConfig:
    return BotConfig(
        token=os.environ["TELEGRAM_TOKEN"],
        repl_url=os.getenv("REPL_URL", "http://localhost:8000"),
    )


# ---------------------------------------------------------------------------
# HTTP client morphisms  (async I/O at the boundary — fallible via Result)
# ---------------------------------------------------------------------------

async def _fetch_health(repl_url: str) -> Ok[HealthStatus] | Err[Exception]:
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            response = await client.get(f"{repl_url}/health")
            data: dict[str, str] = response.json()
            return Ok(HealthStatus(status=data.get("status", "unknown")))
    except Exception as exc:
        return Err(exc)


async def _upload_photo(
    repl_url: str, file_id: str, photo_bytes: bytes
) -> Ok[PhotoUpload] | Err[Exception]:
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                f"{repl_url}/photos/upload",
                files={"file": (f"{file_id}.jpg", photo_bytes, "image/jpeg")},
            )
            data: dict[str, str] = response.json()
            return Ok(PhotoUpload(photo_id=data.get("photo_id", "unknown")))
    except Exception as exc:
        return Err(exc)


async def _upload_audio(
    repl_url: str, file_id: str, audio_bytes: bytes
) -> Ok[AudioUpload] | Err[Exception]:
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                f"{repl_url}/audio/upload",
                files={"file": (f"{file_id}.ogg", audio_bytes, "audio/ogg")},
            )
            data: dict[str, str] = response.json()
            return Ok(AudioUpload(audio_id=data.get("audio_id", "unknown")))
    except Exception as exc:
        return Err(exc)


async def _run_ocr(repl_url: str, photo_id: str) -> Ok[OcrResult] | Err[Exception]:
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(f"{repl_url}/photos/{photo_id}/analyse/ocr")
            data: dict[str, str] = response.json()
            return Ok(OcrResult(text=data.get("text", "").strip()))
    except Exception as exc:
        return Err(exc)


async def _run_transcription(
    repl_url: str, audio_id: str
) -> Ok[TranscriptionResult] | Err[Exception]:
    try:
        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.get(f"{repl_url}/audio/{audio_id}/transcribe")
            data: dict[str, str] = response.json()
            return Ok(TranscriptionResult(text=data.get("text", "").strip()))
    except Exception as exc:
        return Err(exc)


# ---------------------------------------------------------------------------
# Handler factories  (close over BotConfig and SessionState)
# ---------------------------------------------------------------------------

Handler = Callable[[Update, ContextTypes.DEFAULT_TYPE], Awaitable[None]]

HELP_TEXT = (
    "Available commands:\n\n"
    "/hello — check if the REPL service is up\n"
    "/ocr — extract text from your last uploaded photo\n"
    "/transcribe — transcribe your last voice message\n"
    "/help — show this help message\n"
    "/start — show this help message\n\n"
    "To use OCR: send a photo, then run /ocr\n"
    "To transcribe: send a voice message, then run /transcribe"
)


def make_hello_handler(config: BotConfig) -> Handler:
    async def handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        assert update.message is not None
        match await _fetch_health(config.repl_url):
            case Ok(value=health):
                await update.message.reply_text(
                    f"REPL service is up. Status: {health.status}"
                )
            case Err(error=exc):
                await update.message.reply_text(f"REPL service is unreachable: {exc}")

    return handler


def make_photo_handler(config: BotConfig, state: SessionState) -> Handler:
    async def handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        assert update.message is not None
        assert update.message.from_user is not None
        photo = update.message.photo[-1]
        file = await context.bot.get_file(photo.file_id)
        photo_bytes = bytes(await file.download_as_bytearray())

        match await _upload_photo(config.repl_url, photo.file_id, photo_bytes):
            case Ok(value=upload):
                state.last_photo[update.message.from_user.id] = upload.photo_id
                await update.message.reply_text(
                    f"Photo uploaded. ID: {upload.photo_id}\n\n"
                    "Use /ocr to extract text from this photo."
                )
            case Err(error=exc):
                await update.message.reply_text(f"Failed to upload photo: {exc}")

    return handler


def make_voice_handler(config: BotConfig, state: SessionState) -> Handler:
    async def handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        assert update.message is not None
        assert update.message.voice is not None
        assert update.message.from_user is not None
        file = await context.bot.get_file(update.message.voice.file_id)
        audio_bytes = bytes(await file.download_as_bytearray())

        match await _upload_audio(
            config.repl_url, update.message.voice.file_id, audio_bytes
        ):
            case Ok(value=upload):
                state.last_audio[update.message.from_user.id] = upload.audio_id
                await update.message.reply_text(
                    f"Voice message uploaded. ID: {upload.audio_id}\n\n"
                    "Use /transcribe to transcribe it."
                )
            case Err(error=exc):
                await update.message.reply_text(
                    f"Failed to upload voice message: {exc}"
                )

    return handler


def make_ocr_handler(config: BotConfig, state: SessionState) -> Handler:
    async def handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        assert update.message is not None
        assert update.message.from_user is not None

        match state.last_photo.get(update.message.from_user.id):
            case None:
                await update.message.reply_text(
                    "No photo uploaded yet. Send a photo first."
                )
            case photo_id:
                match await _run_ocr(config.repl_url, photo_id):
                    case Ok(value=result):
                        await update.message.reply_text(
                            result.text if result.text else "No text found in the image."
                        )
                    case Err(error=exc):
                        await update.message.reply_text(f"OCR failed: {exc}")

    return handler


def make_transcribe_handler(config: BotConfig, state: SessionState) -> Handler:
    async def handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        assert update.message is not None
        assert update.message.from_user is not None

        match state.last_audio.get(update.message.from_user.id):
            case None:
                await update.message.reply_text(
                    "No voice message uploaded yet. Send a voice message first."
                )
            case audio_id:
                match await _run_transcription(config.repl_url, audio_id):
                    case Ok(value=result):
                        await update.message.reply_text(
                            result.text if result.text else "No speech detected."
                        )
                    case Err(error=exc):
                        await update.message.reply_text(f"Transcription failed: {exc}")

    return handler


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    assert update.message is not None
    await update.message.reply_text(HELP_TEXT)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    assert update.message is not None
    await update.message.reply_text("Hello! " + HELP_TEXT)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    config = _load_config()
    state = SessionState(last_photo={}, last_audio={})

    app = ApplicationBuilder().token(config.token).build()
    app.add_handler(CommandHandler("hello", make_hello_handler(config)))
    app.add_handler(CommandHandler("ocr", make_ocr_handler(config, state)))
    app.add_handler(CommandHandler("transcribe", make_transcribe_handler(config, state)))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.PHOTO, make_photo_handler(config, state)))
    app.add_handler(MessageHandler(filters.VOICE, make_voice_handler(config, state)))
    print("Bot is running. Press Ctrl+C to stop.")
    app.run_polling()


if __name__ == "__main__":
    main()

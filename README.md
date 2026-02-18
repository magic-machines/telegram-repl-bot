# telegram-repl-bot

A Telegram bot backed by a local FastAPI service. Send photos for OCR or voice messages for transcription.

## Architecture

```
Telegram User
     │
     ▼
telegram_bot.py  ──HTTP──▶  repl_service.py (FastAPI :8000)
                                 │
                                 ├── pytesseract (OCR)
                                 └── Whisper base (transcription)
```

## Features

- `/start` — list available commands
- `/hello` — check if the REPL service is up
- Send a **photo** → uploaded and stored; use `/ocr` to extract text
- `/ocr` — run OCR on your last uploaded photo
- Send a **voice message** → uploaded and stored; use `/transcribe` to transcribe
- `/transcribe` — transcribe your last voice message

## Setup

### Prerequisites

- Python 3.12+
- `tesseract-ocr` — `apt-get install tesseract-ocr`
- `ffmpeg` — `apt-get install ffmpeg`

### Install dependencies

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Configure

```bash
cp .env.example .env
# Edit .env and set your TELEGRAM_TOKEN (get one from @BotFather)
```

### Run

```bash
# Terminal 1
python repl_service.py

# Terminal 2
python telegram_bot.py
```

## Service endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Service status |
| POST | `/photos/upload` | Upload a photo |
| GET | `/photos/{id}/analyse/ocr` | Extract text from a photo |
| POST | `/audio/upload` | Upload an audio file |
| GET | `/audio/{id}/transcribe` | Transcribe audio with Whisper |

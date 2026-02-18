import uuid
from pathlib import Path
from fastapi import FastAPI, UploadFile, File, HTTPException
from PIL import Image, ImageFilter, ImageEnhance
import pytesseract
import whisper

PHOTOS_DIR = Path("/tmp/photos")
PHOTOS_DIR.mkdir(exist_ok=True)

AUDIO_DIR = Path("/tmp/audio")
AUDIO_DIR.mkdir(exist_ok=True)

app = FastAPI()

whisper_model = whisper.load_model("base")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/photos/upload")
async def upload_photo(file: UploadFile = File(...)) -> dict[str, str]:
    photo_id = str(uuid.uuid4())
    dest = PHOTOS_DIR / f"{photo_id}_{file.filename}"
    dest.write_bytes(await file.read())
    return {"photo_id": photo_id, "filename": file.filename or ""}


def _correct_rotation(image: Image.Image) -> Image.Image:
    try:
        osd = pytesseract.image_to_osd(image)
        angle = int(next(
            line for line in osd.splitlines() if "Rotate" in line
        ).split(":")[1].strip())
        if angle != 0:
            image = image.rotate(angle, expand=True)
    except Exception:
        pass
    return image


def _preprocess(image: Image.Image) -> Image.Image:
    image = image.convert("L")
    image = ImageEnhance.Contrast(image).enhance(2.0)
    image = image.filter(ImageFilter.SHARPEN)
    return image


@app.get("/photos/{photo_id}/analyse/ocr")
def analyse_ocr(photo_id: str) -> dict[str, str]:
    matches = list(PHOTOS_DIR.glob(f"{photo_id}_*"))
    if not matches:
        raise HTTPException(status_code=404, detail="Photo not found")
    image = _correct_rotation(Image.open(matches[0]))
    image = _preprocess(image)
    config = "--psm 11 --oem 3"
    text = pytesseract.image_to_string(image, config=config)
    return {"photo_id": photo_id, "text": text}


@app.post("/audio/upload")
async def upload_audio(file: UploadFile = File(...)) -> dict[str, str]:
    audio_id = str(uuid.uuid4())
    dest = AUDIO_DIR / f"{audio_id}_{file.filename}"
    dest.write_bytes(await file.read())
    return {"audio_id": audio_id, "filename": file.filename or ""}


@app.get("/audio/{audio_id}/transcribe")
def transcribe_audio(audio_id: str) -> dict[str, str]:
    matches = list(AUDIO_DIR.glob(f"{audio_id}_*"))
    if not matches:
        raise HTTPException(status_code=404, detail="Audio not found")
    result = whisper_model.transcribe(str(matches[0]))
    return {"audio_id": audio_id, "text": result["text"]}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

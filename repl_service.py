from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import TypeVar, Generic, Callable, TypeAlias
import functools

from fastapi import FastAPI, UploadFile, File, HTTPException
from PIL import Image, ImageFilter, ImageEnhance
import pytesseract
import whisper


# ---------------------------------------------------------------------------
# Type machinery
# ---------------------------------------------------------------------------

_F = TypeVar("_F")

Morphism: TypeAlias = Callable[[_F], _F]

A = TypeVar("A")
E = TypeVar("E")


@dataclass(frozen=True)
class Ok(Generic[A]):
    value: A


@dataclass(frozen=True)
class Err(Generic[E]):
    error: E


def pipe(*fns: Callable[[_F], _F]) -> Callable[[_F], _F]:
    """Left-to-right function composition: pipe(f, g)(x) == g(f(x))"""
    return functools.reduce(lambda f, g: lambda x: g(f(x)), fns)  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Domain types
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PhotoId:
    value: str


@dataclass(frozen=True)
class AudioId:
    value: str


@dataclass(frozen=True)
class OcrText:
    text: str


@dataclass(frozen=True)
class TranscriptionText:
    text: str


@dataclass(frozen=True)
class HealthStatus:
    status: str


# ---------------------------------------------------------------------------
# Service configuration
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ServiceConfig:
    photos_dir: Path
    audio_dir: Path


def _init_dir(path: Path) -> Path:
    path.mkdir(exist_ok=True)
    return path


def _make_config() -> ServiceConfig:
    return ServiceConfig(
        photos_dir=_init_dir(Path("/tmp/photos")),
        audio_dir=_init_dir(Path("/tmp/audio")),
    )


_CONFIG = _make_config()

app = FastAPI()

_whisper_model = whisper.load_model("base")


# ---------------------------------------------------------------------------
# Image processing morphisms
# ---------------------------------------------------------------------------

def _to_grayscale(image: Image.Image) -> Image.Image:
    return image.convert("L")


def _enhance_contrast(image: Image.Image) -> Image.Image:
    return ImageEnhance.Contrast(image).enhance(2.0)


def _sharpen(image: Image.Image) -> Image.Image:
    return image.filter(ImageFilter.SHARPEN)


_preprocess: Callable[[Image.Image], Image.Image] = pipe(
    _to_grayscale,
    _enhance_contrast,
    _sharpen,
)


def _get_osd(image: Image.Image) -> Ok[str] | Err[Exception]:
    try:
        return Ok(pytesseract.image_to_osd(image))
    except Exception as exc:
        return Err(exc)


def _parse_rotation_angle(osd: str) -> Ok[int] | Err[Exception]:
    try:
        line = next(ln for ln in osd.splitlines() if "Rotate" in ln)
        return Ok(int(line.split(":")[1].strip()))
    except Exception as exc:
        return Err(exc)


def _apply_rotation(image: Image.Image, angle: int) -> Image.Image:
    return image.rotate(angle, expand=True) if angle != 0 else image


def _correct_rotation(image: Image.Image) -> Image.Image:
    match _get_osd(image):
        case Err():
            return image
        case Ok(value=osd):
            match _parse_rotation_angle(osd):
                case Err():
                    return image
                case Ok(value=angle):
                    return _apply_rotation(image, angle)


# ---------------------------------------------------------------------------
# FastAPI routes
# ---------------------------------------------------------------------------

@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/photos/upload")
async def upload_photo(file: UploadFile = File(...)) -> dict[str, str]:
    photo_id = PhotoId(value=str(uuid.uuid4()))
    dest = _CONFIG.photos_dir / f"{photo_id.value}_{file.filename}"
    dest.write_bytes(await file.read())
    return {"photo_id": photo_id.value, "filename": file.filename or ""}


@app.get("/photos/{photo_id}/analyse/ocr")
def analyse_ocr(photo_id: str) -> dict[str, str]:
    match list(_CONFIG.photos_dir.glob(f"{photo_id}_*")):
        case []:
            raise HTTPException(status_code=404, detail="Photo not found")
        case [first, *_]:
            image = _preprocess(_correct_rotation(Image.open(first)))
            text: str = pytesseract.image_to_string(image, config="--psm 11 --oem 3")
            return {"photo_id": photo_id, "text": text}
    raise HTTPException(status_code=500, detail="Unreachable")


@app.post("/audio/upload")
async def upload_audio(file: UploadFile = File(...)) -> dict[str, str]:
    audio_id = AudioId(value=str(uuid.uuid4()))
    dest = _CONFIG.audio_dir / f"{audio_id.value}_{file.filename}"
    dest.write_bytes(await file.read())
    return {"audio_id": audio_id.value, "filename": file.filename or ""}


@app.get("/audio/{audio_id}/transcribe")
def transcribe_audio(audio_id: str) -> dict[str, str]:
    match list(_CONFIG.audio_dir.glob(f"{audio_id}_*")):
        case []:
            raise HTTPException(status_code=404, detail="Audio not found")
        case [first, *_]:
            raw: dict[str, object] = _whisper_model.transcribe(str(first))  # type: ignore[assignment]
            return {"audio_id": audio_id, "text": str(raw.get("text", ""))}
    raise HTTPException(status_code=500, detail="Unreachable")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

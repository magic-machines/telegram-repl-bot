from __future__ import annotations

import io
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from PIL import Image

# conftest.py has already injected a mock whisper into sys.modules, so importing
# repl_service here will NOT trigger a real whisper.load_model("base") call.
from repl_service import (
    Ok,
    Err,
    app,
    pipe,
    _apply_rotation,
    _enhance_contrast,
    _parse_rotation_angle,
    _sharpen,
    _to_grayscale,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_jpeg_bytes(width: int = 100, height: int = 100) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (width, height)).save(buf, format="JPEG")
    buf.seek(0)
    return buf.read()


@pytest.fixture(name="client")
def _client() -> TestClient:
    return TestClient(app)


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


def test_ok_holds_value() -> None:
    ok: Ok[int] = Ok(42)
    assert ok.value == 42


def test_err_holds_error() -> None:
    exc = ValueError("oops")
    err: Err[Exception] = Err(exc)
    assert err.error is exc


def test_ok_is_immutable() -> None:
    ok = Ok(1)
    with pytest.raises(AttributeError):
        ok.value = 2  # type: ignore[misc]


def test_err_is_immutable() -> None:
    err = Err("boom")
    with pytest.raises(AttributeError):
        err.error = "other"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# pipe()
# ---------------------------------------------------------------------------


def test_pipe_single_function() -> None:
    double = lambda x: x * 2  # noqa: E731
    assert pipe(double)(3) == 6


def test_pipe_two_functions() -> None:
    double = lambda x: x * 2  # noqa: E731
    add_one = lambda x: x + 1  # noqa: E731
    assert pipe(double, add_one)(3) == 7  # 3*2=6, 6+1=7


def test_pipe_three_functions() -> None:
    double = lambda x: x * 2  # noqa: E731
    add_one = lambda x: x + 1  # noqa: E731
    negate = lambda x: -x  # noqa: E731
    assert pipe(double, add_one, negate)(3) == -7


# ---------------------------------------------------------------------------
# Image morphisms
# ---------------------------------------------------------------------------


def test_to_grayscale_converts_mode() -> None:
    img = Image.new("RGB", (10, 10), color=(255, 0, 0))
    result = _to_grayscale(img)
    assert result.mode == "L"


def test_enhance_contrast_returns_image() -> None:
    img = Image.new("L", (10, 10))
    result = _enhance_contrast(img)
    assert isinstance(result, Image.Image)


def test_sharpen_returns_image() -> None:
    img = Image.new("L", (10, 10))
    result = _sharpen(img)
    assert isinstance(result, Image.Image)


# ---------------------------------------------------------------------------
# _parse_rotation_angle
# ---------------------------------------------------------------------------


def test_parse_rotation_angle_valid() -> None:
    osd = "Page number: 0\nOrientation in degrees: 0\nRotate: 90\nOrientation confidence: 1.23\n"
    result = _parse_rotation_angle(osd)
    assert isinstance(result, Ok)
    assert result.value == 90


def test_parse_rotation_angle_zero() -> None:
    result = _parse_rotation_angle("Rotate: 0\n")
    assert isinstance(result, Ok)
    assert result.value == 0


def test_parse_rotation_angle_no_rotate_line() -> None:
    result = _parse_rotation_angle("Orientation: 0\n")
    assert isinstance(result, Err)


# ---------------------------------------------------------------------------
# _apply_rotation
# ---------------------------------------------------------------------------


def test_apply_rotation_zero_returns_same_object() -> None:
    img = Image.new("RGB", (100, 50))
    assert _apply_rotation(img, 0) is img


def test_apply_rotation_ninety_swaps_dimensions() -> None:
    img = Image.new("RGB", (100, 50))
    result = _apply_rotation(img, 90)
    assert result is not img
    # 90-degree rotation with expand=True swaps width and height
    assert result.size == (50, 100)


# ---------------------------------------------------------------------------
# API: /health
# ---------------------------------------------------------------------------


def test_health_returns_ok(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


# ---------------------------------------------------------------------------
# API: /photos/upload
# ---------------------------------------------------------------------------


def test_upload_photo_returns_photo_id(client: TestClient) -> None:
    response = client.post(
        "/photos/upload",
        files={"file": ("test.jpg", _make_jpeg_bytes(), "image/jpeg")},
    )
    assert response.status_code == 200
    data = response.json()
    assert "photo_id" in data
    assert data["filename"] == "test.jpg"


def test_upload_photo_id_is_unique(client: TestClient) -> None:
    ids = {
        client.post(
            "/photos/upload",
            files={"file": ("img.jpg", _make_jpeg_bytes(), "image/jpeg")},
        ).json()["photo_id"]
        for _ in range(3)
    }
    assert len(ids) == 3


# ---------------------------------------------------------------------------
# API: /photos/{photo_id}/analyse/ocr
# ---------------------------------------------------------------------------


def test_ocr_unknown_photo_returns_404(client: TestClient) -> None:
    response = client.get("/photos/does-not-exist/analyse/ocr")
    assert response.status_code == 404


def test_ocr_uploaded_photo(client: TestClient) -> None:
    upload = client.post(
        "/photos/upload",
        files={"file": ("ocr.jpg", _make_jpeg_bytes(), "image/jpeg")},
    )
    photo_id = upload.json()["photo_id"]

    with (
        patch("repl_service.pytesseract.image_to_osd", side_effect=Exception("no osd")),
        patch("repl_service.pytesseract.image_to_string", return_value="Hello World"),
    ):
        response = client.get(f"/photos/{photo_id}/analyse/ocr")

    assert response.status_code == 200
    data = response.json()
    assert data["photo_id"] == photo_id
    assert data["text"] == "Hello World"


# ---------------------------------------------------------------------------
# API: /audio/upload
# ---------------------------------------------------------------------------


def test_upload_audio_returns_audio_id(client: TestClient) -> None:
    response = client.post(
        "/audio/upload",
        files={"file": ("voice.ogg", b"fake audio bytes", "audio/ogg")},
    )
    assert response.status_code == 200
    data = response.json()
    assert "audio_id" in data
    assert data["filename"] == "voice.ogg"


# ---------------------------------------------------------------------------
# API: /audio/{audio_id}/transcribe
# ---------------------------------------------------------------------------


def test_transcribe_unknown_audio_returns_404(client: TestClient) -> None:
    response = client.get("/audio/does-not-exist/transcribe")
    assert response.status_code == 404


def test_transcribe_uploaded_audio(client: TestClient) -> None:
    upload = client.post(
        "/audio/upload",
        files={"file": ("voice.ogg", b"fake audio bytes", "audio/ogg")},
    )
    audio_id = upload.json()["audio_id"]

    # The mock model is configured in conftest.py to return {"text": "mocked transcription"}
    response = client.get(f"/audio/{audio_id}/transcribe")

    assert response.status_code == 200
    data = response.json()
    assert data["audio_id"] == audio_id
    assert data["text"] == "mocked transcription"

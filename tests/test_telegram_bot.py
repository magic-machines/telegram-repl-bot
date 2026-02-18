from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from telegram_bot import (
    AudioUpload,
    BotConfig,
    Err,
    HELP_TEXT,
    Ok,
    OcrResult,
    PhotoUpload,
    SessionState,
    TranscriptionResult,
    _fetch_health,
    _run_ocr,
    _run_transcription,
    _upload_audio,
    _upload_photo,
)


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


def test_ok_holds_value() -> None:
    ok: Ok[str] = Ok("hello")
    assert ok.value == "hello"


def test_err_holds_error() -> None:
    exc = RuntimeError("bang")
    err: Err[Exception] = Err(exc)
    assert err.error is exc


def test_ok_is_immutable() -> None:
    ok = Ok(1)
    with pytest.raises(AttributeError):
        ok.value = 2  # type: ignore[misc]


def test_err_is_immutable() -> None:
    err = Err("oops")
    with pytest.raises(AttributeError):
        err.error = "other"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Domain types
# ---------------------------------------------------------------------------


def test_bot_config_stores_fields() -> None:
    cfg = BotConfig(token="tok123", repl_url="http://localhost:8000")
    assert cfg.token == "tok123"
    assert cfg.repl_url == "http://localhost:8000"


def test_bot_config_is_immutable() -> None:
    cfg = BotConfig(token="tok", repl_url="http://localhost")
    with pytest.raises(AttributeError):
        cfg.token = "other"  # type: ignore[misc]


def test_session_state_tracks_photos() -> None:
    state = SessionState(last_photo={}, last_audio={})
    state.last_photo[1] = "photo-uuid-1"
    assert state.last_photo[1] == "photo-uuid-1"


def test_session_state_tracks_audio() -> None:
    state = SessionState(last_photo={}, last_audio={})
    state.last_audio[42] = "audio-uuid-42"
    assert state.last_audio[42] == "audio-uuid-42"


def test_session_state_independent_users() -> None:
    state = SessionState(last_photo={}, last_audio={})
    state.last_photo[1] = "p1"
    state.last_photo[2] = "p2"
    assert state.last_photo[1] == "p1"
    assert state.last_photo[2] == "p2"


# ---------------------------------------------------------------------------
# HELP_TEXT
# ---------------------------------------------------------------------------


def test_help_text_mentions_all_commands() -> None:
    for cmd in ("/hello", "/ocr", "/transcribe", "/help", "/start"):
        assert cmd in HELP_TEXT


# ---------------------------------------------------------------------------
# HTTP morphisms — tested via mocked httpx.AsyncClient
# ---------------------------------------------------------------------------


def _mock_client_ctx(response_json: dict) -> AsyncMock:
    """Return a mock async client wired up with the given JSON response.

    httpx Response.json() is synchronous, so the response itself is a plain
    MagicMock; the client methods (get/post) are async, so they use AsyncMock.
    """
    mock_response = MagicMock()
    mock_response.json.return_value = response_json
    mock_client = AsyncMock()
    mock_client.get.return_value = mock_response
    mock_client.post.return_value = mock_response
    return mock_client


@pytest.mark.asyncio
async def test_fetch_health_success() -> None:
    mock_client = _mock_client_ctx({"status": "ok"})
    with patch("telegram_bot.httpx.AsyncClient") as cls:
        cls.return_value.__aenter__.return_value = mock_client
        result = await _fetch_health("http://localhost:8000")
    assert isinstance(result, Ok)
    assert result.value.status == "ok"


@pytest.mark.asyncio
async def test_fetch_health_unknown_status() -> None:
    mock_client = _mock_client_ctx({})
    with patch("telegram_bot.httpx.AsyncClient") as cls:
        cls.return_value.__aenter__.return_value = mock_client
        result = await _fetch_health("http://localhost:8000")
    assert isinstance(result, Ok)
    assert result.value.status == "unknown"


@pytest.mark.asyncio
async def test_fetch_health_network_error() -> None:
    mock_client = AsyncMock()
    mock_client.get.side_effect = Exception("connection refused")
    with patch("telegram_bot.httpx.AsyncClient") as cls:
        cls.return_value.__aenter__.return_value = mock_client
        result = await _fetch_health("http://localhost:8000")
    assert isinstance(result, Err)


@pytest.mark.asyncio
async def test_upload_photo_success() -> None:
    mock_client = _mock_client_ctx({"photo_id": "abc-123", "filename": "f.jpg"})
    with patch("telegram_bot.httpx.AsyncClient") as cls:
        cls.return_value.__aenter__.return_value = mock_client
        result = await _upload_photo("http://localhost:8000", "file123", b"bytes")
    assert isinstance(result, Ok)
    assert isinstance(result.value, PhotoUpload)
    assert result.value.photo_id == "abc-123"


@pytest.mark.asyncio
async def test_upload_photo_network_error() -> None:
    mock_client = AsyncMock()
    mock_client.post.side_effect = Exception("timeout")
    with patch("telegram_bot.httpx.AsyncClient") as cls:
        cls.return_value.__aenter__.return_value = mock_client
        result = await _upload_photo("http://localhost:8000", "fid", b"b")
    assert isinstance(result, Err)


@pytest.mark.asyncio
async def test_upload_audio_success() -> None:
    mock_client = _mock_client_ctx({"audio_id": "def-456", "filename": "v.ogg"})
    with patch("telegram_bot.httpx.AsyncClient") as cls:
        cls.return_value.__aenter__.return_value = mock_client
        result = await _upload_audio("http://localhost:8000", "fid", b"bytes")
    assert isinstance(result, Ok)
    assert isinstance(result.value, AudioUpload)
    assert result.value.audio_id == "def-456"


@pytest.mark.asyncio
async def test_run_ocr_success() -> None:
    mock_client = _mock_client_ctx({"photo_id": "abc-123", "text": "  Hello OCR  "})
    with patch("telegram_bot.httpx.AsyncClient") as cls:
        cls.return_value.__aenter__.return_value = mock_client
        result = await _run_ocr("http://localhost:8000", "abc-123")
    assert isinstance(result, Ok)
    assert isinstance(result.value, OcrResult)
    assert result.value.text == "Hello OCR"  # stripped


@pytest.mark.asyncio
async def test_run_ocr_network_error() -> None:
    mock_client = AsyncMock()
    mock_client.get.side_effect = Exception("timeout")
    with patch("telegram_bot.httpx.AsyncClient") as cls:
        cls.return_value.__aenter__.return_value = mock_client
        result = await _run_ocr("http://localhost:8000", "abc-123")
    assert isinstance(result, Err)


@pytest.mark.asyncio
async def test_run_transcription_success() -> None:
    mock_client = _mock_client_ctx({"audio_id": "def-456", "text": "  Hi there  "})
    with patch("telegram_bot.httpx.AsyncClient") as cls:
        cls.return_value.__aenter__.return_value = mock_client
        result = await _run_transcription("http://localhost:8000", "def-456")
    assert isinstance(result, Ok)
    assert isinstance(result.value, TranscriptionResult)
    assert result.value.text == "Hi there"  # stripped


@pytest.mark.asyncio
async def test_run_transcription_network_error() -> None:
    mock_client = AsyncMock()
    mock_client.get.side_effect = Exception("timeout")
    with patch("telegram_bot.httpx.AsyncClient") as cls:
        cls.return_value.__aenter__.return_value = mock_client
        result = await _run_transcription("http://localhost:8000", "def-456")
    assert isinstance(result, Err)

from __future__ import annotations

import sys
from unittest.mock import MagicMock

# Inject a mock whisper module into sys.modules BEFORE repl_service is imported.
# This prevents whisper.load_model("base") from downloading the model at import time,
# making tests fast and runnable in CI without a GPU or model cache.
_mock_model = MagicMock()
_mock_model.transcribe.return_value = {"text": "mocked transcription"}

_mock_whisper = MagicMock()
_mock_whisper.load_model.return_value = _mock_model

sys.modules["whisper"] = _mock_whisper

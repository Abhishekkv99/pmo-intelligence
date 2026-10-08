"""AssemblyAI transcription: settings applied, submitted once, polled to the end,
and every failure (refused, failed, timed out, unreachable) a TranscriptionError."""

from types import SimpleNamespace
from typing import Any

import assemblyai as aai
import httpx
import pytest

from app.config import settings
from app.services.transcription import assemblyai_client
from app.utils.exceptions import TranscriptionError


def _response(status: aai.TranscriptStatus, **fields: Any) -> SimpleNamespace:
    base: dict[str, Any] = {
        "id": "t-1",
        "status": status,
        "text": None,
        "utterances": None,
        "audio_duration": None,
        "error": None,
    }
    return SimpleNamespace(**{**base, **fields})


class _FakeSdk:
    def __init__(self, responses: list[SimpleNamespace]) -> None:
        self.responses = responses
        self.submitted: list[tuple[str, aai.TranscriptionConfig]] = []
        self.fetches = 0

    def submit(self, media: str, config: aai.TranscriptionConfig) -> str:
        self.submitted.append((media, config))
        return "t-1"

    def fetch(self, transcript_id: str) -> SimpleNamespace:
        self.fetches += 1
        return self.responses.pop(0)


@pytest.fixture
def sdk(monkeypatch: pytest.MonkeyPatch) -> _FakeSdk:
    fake = _FakeSdk([])
    monkeypatch.setattr(assemblyai_client, "_submit", fake.submit)
    monkeypatch.setattr(assemblyai_client, "_fetch", fake.fetch)
    monkeypatch.setattr(settings, "assemblyai_poll_interval_seconds", 0.0)
    return fake


class TestTranscribeMedia:
    async def test_polls_until_completed_and_returns_the_utterances(
        self, sdk: _FakeSdk
    ) -> None:
        utterance = SimpleNamespace(
            speaker="A", text="Morning.", start=0, end=900, confidence=0.97
        )
        sdk.responses = [
            _response(aai.TranscriptStatus.queued),
            _response(aai.TranscriptStatus.processing),
            _response(
                aai.TranscriptStatus.completed,
                text="Morning.",
                utterances=[utterance],
                audio_duration=1,
            ),
        ]

        result = await assemblyai_client.transcribe_media("https://media/r.webm")

        assert sdk.fetches == 3
        assert result.transcript_id == "t-1"
        assert result.text == "Morning."
        assert result.audio_duration_seconds == 1.0
        assert result.utterances == [
            {
                "speaker": "A",
                "text": "Morning.",
                "start_ms": 0,
                "end_ms": 900,
                "confidence": 0.97,
            }
        ]

    async def test_settings_set_the_region_models_and_speaker_range(
        self, sdk: _FakeSdk, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "assemblyai_api_key", "pmo-key")
        sdk.responses = [_response(aai.TranscriptStatus.completed)]

        await assemblyai_client.transcribe_media("https://media/r.webm")

        _, config = sdk.submitted[0]
        assert aai.settings.base_url == settings.assemblyai_base_url
        assert aai.settings.api_key == "pmo-key"
        assert config.speaker_labels is True
        assert config.speech_models == settings.assemblyai_speech_models
        options = config.speaker_options
        assert options is not None
        assert options.min_speakers_expected == 2
        assert options.max_speakers_expected == 4

    async def test_failed_transcript_is_an_error_with_assemblyai_s_reason(
        self, sdk: _FakeSdk
    ) -> None:
        sdk.responses = [_response(aai.TranscriptStatus.error, error="audio too short")]

        with pytest.raises(TranscriptionError, match="audio too short"):
            await assemblyai_client.transcribe_media("https://media/r.webm")

    async def test_transcript_still_running_at_the_timeout_is_an_error(
        self, sdk: _FakeSdk, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "assemblyai_timeout_seconds", 0.05)
        monkeypatch.setattr(settings, "assemblyai_poll_interval_seconds", 0.01)
        sdk.responses = [_response(aai.TranscriptStatus.processing)] * 1000

        with pytest.raises(TranscriptionError, match="did not finish within"):
            await assemblyai_client.transcribe_media("https://media/r.webm")

    @pytest.mark.parametrize(
        "error",
        [aai.types.TranscriptError("bad request"), httpx.ConnectError("down")],
    )
    async def test_request_failure_is_an_error(
        self, sdk: _FakeSdk, monkeypatch: pytest.MonkeyPatch, error: Exception
    ) -> None:
        def fail(transcript_id: str) -> None:
            raise error

        monkeypatch.setattr(assemblyai_client, "_fetch", fail)

        with pytest.raises(TranscriptionError, match="request failed"):
            await assemblyai_client.transcribe_media("https://media/r.webm")

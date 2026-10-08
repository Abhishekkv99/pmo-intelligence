"""Diarized transcription of a session recording with AssemblyAI.

Submits the job, then polls its status asynchronously, so the timeout is a
real one: when ``assemblyai_timeout_seconds`` passes, or the job is cancelled
at shutdown, polling stops and no thread is left waiting on AssemblyAI. The
SDK is synchronous, so each short HTTP call (the submit, which also uploads a
local file in development, and every status read) runs in a worker thread.

Region, models and the speaker-count hint come from settings: the EU endpoint
by default, so workers' calls are transcribed and stored in the EU.
"""

import asyncio
import logging
from dataclasses import dataclass
from typing import Any

import assemblyai as aai
import httpx
from assemblyai import api as aai_api
from assemblyai.client import Client

from app.config import settings
from app.utils.exceptions import TranscriptionError

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Transcription:
    transcript_id: str
    text: str
    # Each ``{"speaker", "text", "start_ms", "end_ms", "confidence"}``.
    utterances: list[dict[str, Any]]
    audio_duration_seconds: float | None


def _configure() -> aai.TranscriptionConfig:
    aai.settings.api_key = settings.assemblyai_api_key
    aai.settings.base_url = settings.assemblyai_base_url
    return aai.TranscriptionConfig(
        speaker_labels=True,
        speech_models=settings.assemblyai_speech_models,
        speaker_options=aai.SpeakerOptions(
            min_speakers_expected=settings.assemblyai_min_speakers,
            max_speakers_expected=settings.assemblyai_max_speakers,
        ),
    )


def _submit(media: str, config: aai.TranscriptionConfig) -> str:
    transcript = aai.Transcriber().submit(media, config=config)
    if transcript.status == aai.TranscriptStatus.error or not transcript.id:
        raise TranscriptionError(f"AssemblyAI refused the job: {transcript.error}")
    return str(transcript.id)


def _fetch(transcript_id: str) -> Any:
    return aai_api.get_transcript(Client.get_default().http_client, transcript_id)


def _result(response: Any) -> Transcription:
    utterances = [
        {
            "speaker": u.speaker,
            "text": u.text,
            "start_ms": u.start,
            "end_ms": u.end,
            "confidence": u.confidence,
        }
        for u in response.utterances or []
    ]
    duration = response.audio_duration
    return Transcription(
        transcript_id=str(response.id),
        text=response.text or "",
        utterances=utterances,
        audio_duration_seconds=float(duration) if duration is not None else None,
    )


async def transcribe_media(media: str) -> Transcription:
    """Transcribe the recording at ``media`` (a URL, or a local path in development).

    Raises TranscriptionError when AssemblyAI refuses or fails the job, when a
    request to it fails, or when the job outlasts the configured timeout.
    """
    config = _configure()
    timeout = settings.assemblyai_timeout_seconds
    transcript_id: str | None = None
    try:
        async with asyncio.timeout(timeout):
            transcript_id = await asyncio.to_thread(_submit, media, config)
            logger.info("AssemblyAI transcript %s submitted", transcript_id)
            while True:
                response = await asyncio.to_thread(_fetch, transcript_id)
                if response.status == aai.TranscriptStatus.completed:
                    return _result(response)
                if response.status == aai.TranscriptStatus.error:
                    raise TranscriptionError(
                        f"AssemblyAI failed transcript {transcript_id}: "
                        f"{response.error}"
                    )
                await asyncio.sleep(settings.assemblyai_poll_interval_seconds)
    except TimeoutError as exc:
        raise TranscriptionError(
            f"AssemblyAI transcript {transcript_id} did not finish within {timeout} s"
        ) from exc
    except (aai.types.AssemblyAIError, httpx.HTTPError, OSError) as exc:
        raise TranscriptionError(f"AssemblyAI request failed: {exc}") from exc

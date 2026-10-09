"""The end-to-end seed: development only, and its quotes pass the real check."""

import pytest

from app.cli import seed_e2e_session as seed
from app.config import settings
from app.services.quote_check import TranscriptIndex


@pytest.fixture
def transcript() -> TranscriptIndex:
    utterances = [
        {"speaker": s, "text": t, "start_ms": start, "end_ms": end}
        for s, t, start, end in seed.UTTERANCES
    ]
    return TranscriptIndex(utterances, None)


class TestRefusal:
    def test_refused_when_local_sign_in_is_off(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setattr(settings, "local_auth_enabled", False)
        monkeypatch.setattr(settings, "storage_backend", "local")

        assert seed.main(["--run", "x"]) == 2
        assert "Refused" in capsys.readouterr().err

    def test_refused_on_s3_storage(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(settings, "local_auth_enabled", True)
        monkeypatch.setattr(settings, "storage_backend", "s3")

        assert seed.main(["--run", "x"]) == 2


class TestQuotes:
    @pytest.mark.parametrize(
        ("quote", "offset_ms"),
        [
            (seed.ISSUE_QUOTE, 5_000),
            (seed.ACTION_QUOTE, 10_000),
            (seed.RELATIONSHIP_QUOTE, 15_000),
        ],
    )
    def test_every_quote_is_in_the_transcript_where_it_is_placed(
        self, transcript: TranscriptIndex, quote: str, offset_ms: int
    ) -> None:
        match = transcript.find(quote)
        assert match is not None
        assert match.offset_ms == offset_ms

"""The end-to-end seed: development only, and its quotes pass the real check."""

from datetime import UTC, date, datetime

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
            (seed.CLIENT_QUOTE, 20_000),
        ],
    )
    def test_every_quote_is_in_the_transcript_where_it_is_placed(
        self, transcript: TranscriptIndex, quote: str, offset_ms: int
    ) -> None:
        match = transcript.find(quote)
        assert match is not None
        assert match.offset_ms == offset_ms


class TestHealthDates:
    def test_dates_sit_around_today_for_the_board(self) -> None:
        dates = seed.health_dates(date(2026, 10, 20))

        assert dates.start == date(2026, 8, 21)
        assert dates.expected_end == date(2026, 11, 9)
        assert dates.due == date(2026, 10, 22)
        # Noon in London (BST) three days before.
        assert dates.held_at == datetime(2026, 10, 17, 11, 0, tzinfo=UTC)

    def test_the_call_is_at_noon_uk_time_in_winter_too(self) -> None:
        dates = seed.health_dates(date(2026, 12, 10))

        assert dates.held_at == datetime(2026, 12, 7, 12, 0, tzinfo=UTC)

    def test_health_and_failed_cannot_be_combined(self) -> None:
        with pytest.raises(SystemExit) as exit_:
            seed.main(["--run", "x", "--health", "--failed"])
        assert exit_.value.code == 2

"""The Teams end-to-end seed: development only, and its titles read as stored."""

import pytest

from app.cli import seed_e2e_teams as seed
from app.config import settings
from app.services.teams.chat_titles import TitleFormatError, parse_chat_title


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


class TestTitles:
    def test_the_stored_parts_are_what_the_parser_reads(self) -> None:
        titles = seed.titles("r1")

        unmatched = parse_chat_title(titles["unmatched"])
        matched = parse_chat_title(titles["matched"])

        assert (unmatched.stack, unmatched.consultant, unmatched.client) == (
            "DS",
            "Nia r1",
            "Teams Client r1",
        )
        assert (matched.consultant, matched.start_date, matched.end_date) == (
            "Omar r1",
            seed.START,
            seed.END,
        )
        with pytest.raises(TitleFormatError):
            parse_chat_title(titles["unparsed"])

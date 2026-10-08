"""Settings defaults that matter outside development."""

from pathlib import Path

import pytest

from app.config import Settings


@pytest.fixture(autouse=True)
def _no_env_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    # Settings reads .env from the working directory; a developer's own
    # backend/.env must not decide the default under test.
    monkeypatch.chdir(tmp_path)


def test_debug_is_off_unless_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("APP_DEBUG", raising=False)

    assert Settings().app_debug is False


def test_debug_is_on_when_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_DEBUG", "true")

    assert Settings().app_debug is True

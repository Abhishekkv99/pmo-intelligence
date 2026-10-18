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


def test_transcription_defaults_to_the_eu_endpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("ASSEMBLYAI_BASE_URL", raising=False)
    monkeypatch.delenv("ASSEMBLYAI_SPEECH_MODELS", raising=False)

    s = Settings()

    assert s.assemblyai_base_url == "https://api.eu.assemblyai.com"
    assert s.assemblyai_speech_models == ["universal-3-5-pro", "universal-2"]


def test_speech_models_read_from_json(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ASSEMBLYAI_SPEECH_MODELS", '["universal-2"]')

    assert Settings().assemblyai_speech_models == ["universal-2"]


def test_session_node_timeout_is_under_the_client_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in (
        "SESSION_NODE_TIMEOUT_SECONDS",
        "AZURE_OPENAI_TIMEOUT_SECONDS",
        "SESSION_REASONING_EFFORT",
        "SESSION_RESOLVED_ISSUE_LOOKBACK_DAYS",
    ):
        monkeypatch.delenv(name, raising=False)

    s = Settings()

    # The node's own limit must fire first, so it is recorded as a node error.
    assert s.session_node_timeout_seconds < s.azure_openai_timeout_seconds
    assert s.session_reasoning_effort == "medium"
    assert s.session_resolved_issue_lookback_days == 30


def test_teams_is_off_with_finite_graph_limits_unless_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in (
        "TEAMS_ENABLED",
        "GRAPH_TIMEOUT_SECONDS",
        "GRAPH_MAX_RETRIES",
        "TEAMS_DISCOVERY_ACCOUNTS",
    ):
        monkeypatch.delenv(name, raising=False)

    s = Settings()

    assert s.teams_enabled is False
    assert s.graph_timeout_seconds == 30.0
    assert s.graph_max_retries == 5
    assert s.teams_discovery_accounts == []


def test_teams_discovery_accounts_read_from_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "TEAMS_DISCOVERY_ACCOUNTS", '["ana@example.com", "ben@example.com"]'
    )

    assert Settings().teams_discovery_accounts == [
        "ana@example.com",
        "ben@example.com",
    ]

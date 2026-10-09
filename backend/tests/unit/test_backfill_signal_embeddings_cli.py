"""Unit tests for the embedding backfill's arguments (the backfill itself is
covered against Postgres in tests/integration/test_backfill_signal_embeddings.py)."""

from unittest.mock import AsyncMock, patch

import pytest

from app.cli import backfill_signal_embeddings as cli


class TestMain:
    @pytest.mark.parametrize(("argv", "dry_run"), [([], False), (["--dry-run"], True)])
    def test_runs_the_backfill(self, argv: list[str], dry_run: bool) -> None:
        with patch.object(cli, "backfill", new=AsyncMock(return_value=0)) as run:
            assert cli.main(argv) == 0
        run.assert_awaited_once_with(dry_run=dry_run)

    def test_returns_the_backfill_s_exit_code(self) -> None:
        with patch.object(cli, "backfill", new=AsyncMock(return_value=1)):
            assert cli.main([]) == 1

    def test_an_unknown_argument_exits_2(self) -> None:
        with pytest.raises(SystemExit) as exited:
            cli.main(["--all"])
        assert exited.value.code == 2

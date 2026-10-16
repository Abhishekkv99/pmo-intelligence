"""Unit tests for the process memory helpers."""

import logging
from unittest.mock import mock_open, patch

import pytest

from app.config import settings
from app.utils import memory
from app.utils.memory import (
    current_rss_mib,
    log_rss,
    memory_probe,
    start_tracemalloc_if_enabled,
)

_STATUS = "Name:\tuvicorn\nVmPeak:\t  900000 kB\nVmRSS:\t  12600 kB\nThreads:\t4\n"


class TestCurrentRssMib:
    def test_parses_vmrss_from_proc_status(self) -> None:
        with patch("builtins.open", mock_open(read_data=_STATUS)):
            assert current_rss_mib() == pytest.approx(12600 / 1024)

    def test_returns_none_without_procfs(self) -> None:
        with patch("builtins.open", side_effect=FileNotFoundError):
            assert current_rss_mib() is None

    def test_returns_none_when_the_line_is_absent(self) -> None:
        with patch("builtins.open", mock_open(read_data="Name:\tuvicorn\n")):
            assert current_rss_mib() is None

    def test_returns_none_on_a_malformed_line(self) -> None:
        with patch("builtins.open", mock_open(read_data="VmRSS: lots\n")):
            assert current_rss_mib() is None


class TestLogRss:
    def test_logs_stage_value_and_extra_fields(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        logger = logging.getLogger("test.memory")
        with (
            patch.object(memory, "current_rss_mib", return_value=412.34),
            caplog.at_level(logging.INFO, logger="test.memory"),
        ):
            log_rss(logger, "analysis.persisted", session_id="abc")

        assert "rss stage=analysis.persisted rss_mib=412.3 session_id=abc" in (
            caplog.text
        )

    def test_logs_na_without_a_reading(self, caplog: pytest.LogCaptureFixture) -> None:
        logger = logging.getLogger("test.memory")
        with (
            patch.object(memory, "current_rss_mib", return_value=None),
            caplog.at_level(logging.INFO, logger="test.memory"),
        ):
            log_rss(logger, "x")

        assert "rss_mib=n/a" in caplog.text


class TestMemoryProbe:
    async def test_logs_before_after_and_signed_delta(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        logger = logging.getLogger("test.memory")
        with (
            patch.object(memory, "current_rss_mib", side_effect=[100.0, 119.5]),
            caplog.at_level(logging.INFO, logger="test.memory"),
        ):
            async with memory_probe(logger, "job=analyze id=1"):
                pass

        assert (
            "pipeline memory: job=analyze id=1 rss_before=100.0 "
            "rss_after=119.5 delta=+19.5"
        ) in caplog.text

    async def test_logs_even_when_the_block_raises(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        logger = logging.getLogger("test.memory")
        with (
            patch.object(memory, "current_rss_mib", side_effect=[100.0, 90.0]),
            caplog.at_level(logging.INFO, logger="test.memory"),
            pytest.raises(RuntimeError),
        ):
            async with memory_probe(logger, "job=x"):
                raise RuntimeError("boom")

        assert "delta=-10.0" in caplog.text

    async def test_delta_is_na_without_a_reading(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        logger = logging.getLogger("test.memory")
        with (
            patch.object(memory, "current_rss_mib", return_value=None),
            caplog.at_level(logging.INFO, logger="test.memory"),
        ):
            async with memory_probe(logger, "job=x"):
                pass

        assert "rss_before=n/a rss_after=n/a delta=n/a" in caplog.text


class TestStartTracemalloc:
    def test_does_nothing_when_diagnostics_are_off(self) -> None:
        with (
            patch.object(settings, "memory_diagnostics_enabled", False),
            patch("app.utils.memory.tracemalloc.start") as start,
        ):
            assert start_tracemalloc_if_enabled() is False
        start.assert_not_called()

    def test_starts_tracing_when_enabled(self) -> None:
        with (
            patch.object(settings, "memory_diagnostics_enabled", True),
            patch("app.utils.memory.tracemalloc.is_tracing", return_value=False),
            patch("app.utils.memory.tracemalloc.start") as start,
        ):
            assert start_tracemalloc_if_enabled() is True
        start.assert_called_once_with(25)

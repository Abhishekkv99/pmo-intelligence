"""The versioned health configuration and the health enumerations."""

import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from app.config import settings
from app.health.config import (
    CONFIG_DIR,
    HealthConfig,
    load_health_config,
    parse_health_config,
)
from app.models.enums import (
    RISK_TRIGGER_MEANINGS,
    RISK_TRIGGER_SEVERITY,
    SIGNAL_INDICATOR_MEANINGS,
    Dimension,
    FlagSeverity,
    RiskTrigger,
    SignalIndicator,
)


def _v1() -> dict[str, Any]:
    raw: dict[str, Any] = json.loads((CONFIG_DIR / "v1.json").read_text("utf-8"))
    return raw


def _parse(raw: dict[str, Any]) -> HealthConfig:
    return parse_health_config(json.dumps(raw))


class TestV1:
    def test_v1_holds_the_prd_starting_values(self) -> None:
        config = load_health_config("v1")

        assert config.version == "v1"
        assert config.weights == {
            Dimension.DELIVERY: 30,
            Dimension.RELATIONSHIP: 25,
            Dimension.TECHNICAL: 15,
            Dimension.ENGAGEMENT: 15,
            Dimension.COMMUNICATION: 10,
            Dimension.ONBOARDING: 5,
        }
        assert (config.early_days, config.onboarding_early_weight) == (30, 25)
        assert config.half_life_days == 14
        assert config.lookback_days == 90
        assert (config.prior, config.prior_weight) == (7.0, 1.0)
        assert config.values.negative == {1: 5.0, 2: 3.0, 3: 1.0}
        assert (config.rag.green_min, config.rag.amber_min) == (7.0, 5.0)
        assert (config.trend.window_days, config.trend.flat_band) == (14, 0.5)
        assert config.triggers.downward_trend.drop == 1.5
        assert config.triggers.contract_horizon.days == 30

    def test_the_setting_names_a_version_that_exists(self) -> None:
        assert load_health_config(settings.health_config_version).version

    def test_every_config_file_loads_and_names_itself(self) -> None:
        for path in CONFIG_DIR.glob("*.json"):
            assert load_health_config(path.stem).version == path.stem


class TestValidation:
    def test_weights_must_sum_to_100(self) -> None:
        raw = _v1()
        raw["weights"]["delivery"] = 31
        with pytest.raises(ValidationError, match="sum to 100"):
            _parse(raw)

    def test_weights_need_every_dimension(self) -> None:
        raw = _v1()
        del raw["weights"]["communication"]
        raw["weights"]["delivery"] = 40
        with pytest.raises(ValidationError, match="every dimension"):
            _parse(raw)

    def test_an_unknown_dimension_is_refused(self) -> None:
        raw = _v1()
        raw["weights"]["charisma"] = 0
        with pytest.raises(ValidationError):
            _parse(raw)

    def test_a_negative_value_for_every_severity(self) -> None:
        raw = _v1()
        del raw["values"]["negative"]["3"]
        with pytest.raises(ValidationError, match="every severity"):
            _parse(raw)

    def test_amber_must_be_below_green(self) -> None:
        raw = _v1()
        raw["rag"] = {"green_min": 6.0, "amber_min": 6.0}
        with pytest.raises(ValidationError, match="below green_min"):
            _parse(raw)

    def test_an_unknown_key_is_refused(self) -> None:
        raw = _v1()
        raw["half_life"] = 7
        with pytest.raises(ValidationError):
            _parse(raw)

    def test_the_config_is_frozen(self) -> None:
        config = load_health_config("v1")
        with pytest.raises(ValidationError):
            config.prior = 5.0  # type: ignore[misc]


class TestLoading:
    def test_an_unknown_version_is_refused(self) -> None:
        with pytest.raises(ValueError, match="No health configuration"):
            load_health_config("v999")

    def test_a_path_is_not_a_version(self) -> None:
        with pytest.raises(ValueError, match="Not a health configuration version"):
            load_health_config("../v1")

    def test_a_file_naming_another_version_is_refused(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        raw = _v1()
        (tmp_path / "v2.json").write_text(json.dumps(raw), encoding="utf-8")
        monkeypatch.setattr("app.health.config.CONFIG_DIR", tmp_path)
        load_health_config.cache_clear()
        try:
            with pytest.raises(ValueError, match="names itself 'v1'"):
                load_health_config("v2")
        finally:
            load_health_config.cache_clear()


class TestEnumerations:
    def test_every_indicator_and_trigger_has_a_meaning(self) -> None:
        assert set(SIGNAL_INDICATOR_MEANINGS) == set(SignalIndicator)
        assert set(RISK_TRIGGER_MEANINGS) == set(RiskTrigger)

    def test_every_trigger_has_the_prd_severity(self) -> None:
        assert RISK_TRIGGER_SEVERITY == {
            RiskTrigger.GONE_QUIET: FlagSeverity.MEDIUM,
            RiskTrigger.CLIENT_DISSATISFACTION: FlagSeverity.CRITICAL,
            RiskTrigger.REPEATED_BLOCKER: FlagSeverity.HIGH,
            RiskTrigger.DOWNWARD_TREND: FlagSeverity.HIGH,
            RiskTrigger.RELATIONSHIP_STRAIN: FlagSeverity.HIGH,
            RiskTrigger.CONTRACT_HORIZON: FlagSeverity.HIGH,
            RiskTrigger.INTENT_TO_LEAVE: FlagSeverity.CRITICAL,
            RiskTrigger.MISSED_COMMITMENT: FlagSeverity.MEDIUM,
        }

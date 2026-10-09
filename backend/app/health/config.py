"""The health model's numbers: weights, decay, thresholds, trigger conditions.

They are configuration, never literals in the scoring code. Each version is
a JSON file in ``app/health/config/`` (``v1.json``, ...), chosen by the
``HEALTH_CONFIG_VERSION`` setting; every snapshot records the version that
produced it. Changing a number means a new file, reviewed in git, so an old
snapshot can always be explained by the file it names.
"""

import json
from functools import lru_cache
from pathlib import Path
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.enums import SEVERITY_MAX, SEVERITY_MIN, Dimension

CONFIG_DIR = Path(__file__).parent / "config"


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class SignalValues(_Frozen):
    """The value a signal pulls its dimension towards, on the 1-10 scale."""

    positive: float = Field(ge=1, le=10)
    neutral: float = Field(ge=1, le=10)
    # By severity.
    negative: dict[int, float]

    @model_validator(mode="after")
    def _every_severity(self) -> Self:
        if set(self.negative) != set(range(SEVERITY_MIN, SEVERITY_MAX + 1)):
            raise ValueError("negative needs a value for every severity")
        if not all(1 <= value <= 10 for value in self.negative.values()):
            raise ValueError("negative values must be on the 1-10 scale")
        return self


class RagThresholds(_Frozen):
    green_min: float
    amber_min: float

    @model_validator(mode="after")
    def _ordered(self) -> Self:
        if not self.amber_min < self.green_min:
            raise ValueError("amber_min must be below green_min")
        return self


class TrendSettings(_Frozen):
    window_days: int = Field(gt=0)
    # A change within this many points either way is flat.
    flat_band: float = Field(ge=0)


class RepeatedBlocker(_Frozen):
    min_occurrences: int = Field(ge=2)
    # Open for more than this many days since first seen.
    open_days: int = Field(gt=0)


class DownwardTrend(_Frozen):
    # The overall fell by at least this much over the trend window.
    drop: float = Field(gt=0)


class RelationshipStrain(_Frozen):
    window_days: int = Field(gt=0)
    # One negative Relationship signal this severe fires it...
    single_severity: int = Field(ge=SEVERITY_MIN, le=SEVERITY_MAX)
    # ...or pair_count of at least this severity within the window.
    pair_severity: int = Field(ge=SEVERITY_MIN, le=SEVERITY_MAX)
    pair_count: int = Field(ge=2)


class ContractHorizon(_Frozen):
    # The expected end is within this many days (or past).
    days: int = Field(ge=0)


class TriggerSettings(_Frozen):
    repeated_blocker: RepeatedBlocker
    downward_trend: DownwardTrend
    relationship_strain: RelationshipStrain
    contract_horizon: ContractHorizon


class HealthConfig(_Frozen):
    version: str
    # Percent; they sum to 100.
    weights: dict[Dimension, float]
    # In a placement's first early_days, Onboarding weighs
    # onboarding_early_weight and the others shrink in proportion.
    early_days: int = Field(ge=0)
    onboarding_early_weight: float = Field(ge=0, lt=100)
    half_life_days: float = Field(gt=0)
    # Signals older than this are not read; none in it means not scored.
    lookback_days: int = Field(gt=0)
    # Every dimension's average includes the prior with this weight, so one
    # signal moves a score without pinning it, and a dimension with no
    # signals sits at the prior.
    prior: float = Field(ge=1, le=10)
    prior_weight: float = Field(gt=0)
    values: SignalValues
    top_contributors: int = Field(gt=0)
    rag: RagThresholds
    trend: TrendSettings
    triggers: TriggerSettings

    @model_validator(mode="after")
    def _weights(self) -> Self:
        if set(self.weights) != set(Dimension):
            raise ValueError("weights need every dimension, and only those")
        if any(weight < 0 for weight in self.weights.values()):
            raise ValueError("weights cannot be negative")
        if abs(sum(self.weights.values()) - 100) > 1e-9:
            raise ValueError("weights must sum to 100")
        if self.weights[Dimension.ONBOARDING] >= 100:
            raise ValueError("onboarding cannot carry the whole weight")
        return self


def parse_health_config(raw: str) -> HealthConfig:
    return HealthConfig.model_validate(json.loads(raw))


@lru_cache
def load_health_config(version: str) -> HealthConfig:
    """The configuration in ``config/<version>.json``; it must name itself."""
    if not version.isidentifier():
        raise ValueError(f"Not a health configuration version: {version!r}")
    path = CONFIG_DIR / f"{version}.json"
    if not path.is_file():
        raise ValueError(f"No health configuration {version!r} in {CONFIG_DIR}")
    config = parse_health_config(path.read_text(encoding="utf-8"))
    if config.version != version:
        raise ValueError(f"{path.name} names itself {config.version!r}")
    return config

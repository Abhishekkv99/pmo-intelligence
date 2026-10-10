"""The health tables' constraints, and signals.indicator, against a real database.

Pins what the recompute will rely on: enumerated columns limited to their
sets, a not-scored snapshot with empty scores, and at most one open flag per
placement, trigger and subject (a closed flag never blocks a new one).
"""

import uuid
from datetime import UTC, date, datetime

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import (
    Dimension,
    FlagSeverity,
    Polarity,
    RiskLevel,
    RiskTrigger,
    SignalCategory,
    SignalIndicator,
    SnapshotReason,
    SourceKind,
    Trend,
)
from app.models.health import HealthSnapshot, RiskFlag
from app.models.register import Client, Consultant, Placement, Project
from app.models.signal import Signal

NOW = datetime(2026, 10, 20, 6, 0, tzinfo=UTC)


async def _placement(db: AsyncSession) -> Placement:
    client = Client(name="Acme", normalized_name=f"acme-{uuid.uuid4()}")
    consultant = Consultant(full_name="Priya Shah")
    db.add_all([client, consultant])
    await db.flush()
    project = Project(client_id=client.id, name="Data platform")
    db.add(project)
    await db.flush()
    placement = Placement(
        consultant_id=consultant.id, project_id=project.id, start_date=date(2026, 9, 1)
    )
    db.add(placement)
    await db.flush()
    return placement


def _snapshot(placement: Placement, **fields: object) -> HealthSnapshot:
    values: dict[str, object] = {
        "placement_id": placement.id,
        "computed_at": NOW,
        "reason": SnapshotReason.DAILY.value,
        "scored": True,
        "delivery": 7.0,
        "technical": 4.2,
        "relationship": 7.0,
        "engagement": 7.0,
        "onboarding": 7.0,
        "communication": 7.0,
        "overall": 6.6,
        "trend": Trend.DOWN.value,
        "trend_delta": -0.9,
        "risk_level": RiskLevel.AMBER.value,
        "signal_count": 1,
        "weights_version": "v1",
    }
    values.update(fields)
    return HealthSnapshot(**values)


def _flag(placement: Placement, **fields: object) -> RiskFlag:
    values: dict[str, object] = {
        "placement_id": placement.id,
        "trigger": RiskTrigger.CONTRACT_HORIZON.value,
        "severity": FlagSeverity.HIGH.value,
        "opened_at": NOW,
    }
    values.update(fields)
    return RiskFlag(**values)


class TestSnapshots:
    async def test_a_not_scored_snapshot_has_no_scores(
        self, db_session: AsyncSession
    ) -> None:
        snapshot = HealthSnapshot(
            placement_id=(await _placement(db_session)).id,
            computed_at=NOW,
            reason=SnapshotReason.REGISTER.value,
            scored=False,
            weights_version="v1",
        )
        db_session.add(snapshot)
        await db_session.flush()
        await db_session.refresh(snapshot)

        assert snapshot.overall is None
        assert snapshot.risk_level is None
        assert snapshot.signal_count == 0
        assert snapshot.evidence == {}

    async def test_evidence_round_trips_as_json(self, db_session: AsyncSession) -> None:
        signal_id = str(uuid.uuid4())
        evidence = {
            "technical": {
                "count": 1,
                "top": [{"signal_id": signal_id, "weight": 0.9, "value": 1.0}],
            }
        }
        snapshot = _snapshot(await _placement(db_session), evidence=evidence)
        db_session.add(snapshot)
        await db_session.flush()
        await db_session.refresh(snapshot)

        assert snapshot.evidence == evidence

    @pytest.mark.parametrize(
        ("field", "value"),
        [
            ("reason", "manual"),
            ("trend", "sideways"),
            ("technical_trend", "sideways"),
            ("risk_level", "blue"),
        ],
    )
    async def test_a_value_outside_its_set_is_refused(
        self, db_session: AsyncSession, field: str, value: object
    ) -> None:
        db_session.add(_snapshot(await _placement(db_session), **{field: value}))
        with pytest.raises(IntegrityError):
            await db_session.flush()


class TestFlags:
    async def test_a_new_flag_has_no_subject_and_no_evidence(
        self, db_session: AsyncSession
    ) -> None:
        flag = _flag(await _placement(db_session))
        db_session.add(flag)
        await db_session.flush()
        await db_session.refresh(flag)

        assert flag.subject_key == ""
        assert flag.evidence_signal_ids == []
        assert flag.closed_at is None

    async def test_evidence_ids_round_trip(self, db_session: AsyncSession) -> None:
        ids = [uuid.uuid4(), uuid.uuid4()]
        flag = _flag(await _placement(db_session), evidence_signal_ids=ids)
        db_session.add(flag)
        await db_session.flush()
        await db_session.refresh(flag)

        assert flag.evidence_signal_ids == ids

    async def test_a_second_open_flag_for_the_same_subject_is_refused(
        self, db_session: AsyncSession
    ) -> None:
        placement = await _placement(db_session)
        db_session.add(_flag(placement))
        await db_session.flush()

        db_session.add(_flag(placement))
        with pytest.raises(IntegrityError):
            await db_session.flush()

    async def test_a_closed_flag_does_not_block_a_new_one(
        self, db_session: AsyncSession
    ) -> None:
        placement = await _placement(db_session)
        db_session.add(_flag(placement, closed_at=NOW, closing_note="Extended"))
        db_session.add(_flag(placement))
        await db_session.flush()

    async def test_each_issue_has_its_own_open_flag(
        self, db_session: AsyncSession
    ) -> None:
        placement = await _placement(db_session)
        for _ in range(2):
            db_session.add(
                _flag(
                    placement,
                    trigger=RiskTrigger.REPEATED_BLOCKER.value,
                    subject_key=str(uuid.uuid4()),
                )
            )
        await db_session.flush()

    @pytest.mark.parametrize(
        ("field", "value"), [("trigger", "bad_vibes"), ("severity", "low")]
    )
    async def test_a_value_outside_its_set_is_refused(
        self, db_session: AsyncSession, field: str, value: object
    ) -> None:
        db_session.add(_flag(await _placement(db_session), **{field: value}))
        with pytest.raises(IntegrityError):
            await db_session.flush()


class TestSignalIndicator:
    def _signal(self, placement: Placement, indicator: str | None) -> Signal:
        return Signal(
            placement_id=placement.id,
            source_kind=SourceKind.SESSION.value,
            source_id=uuid.uuid4(),
            category=SignalCategory.CLIENT.value,
            dimension=Dimension.DELIVERY.value,
            polarity=Polarity.NEGATIVE.value,
            severity=3,
            confidence=0.9,
            quote="They've asked whether someone else could take this on",
            occurred_at=NOW,
            indicator=indicator,
        )

    @pytest.mark.parametrize("indicator", [None, *[i.value for i in SignalIndicator]])
    async def test_an_indicator_in_the_set_or_none_is_stored(
        self, db_session: AsyncSession, indicator: str | None
    ) -> None:
        signal = self._signal(await _placement(db_session), indicator)
        db_session.add(signal)
        await db_session.flush()
        await db_session.refresh(signal)

        assert signal.indicator == indicator

    async def test_an_unknown_indicator_is_refused(
        self, db_session: AsyncSession
    ) -> None:
        db_session.add(self._signal(await _placement(db_session), "grumpy"))
        with pytest.raises(IntegrityError):
            await db_session.flush()

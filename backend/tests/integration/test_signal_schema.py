"""The signals, issues and actions tables' constraints against a real database.

Pins what the session pipeline's persistence relies on: enumerated columns
limited to their sets, severity and confidence in range, defaults for a new
issue and action, and a signal outliving the issue it was linked to.
"""

import uuid
from datetime import UTC, date, datetime

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import (
    ActionStatus,
    Dimension,
    IssueStatus,
    Polarity,
    SignalCategory,
    SourceKind,
    SpeakerRole,
)
from app.models.register import Client, Consultant, Placement, Project
from app.models.signal import Action, Issue, Signal

NOW = datetime(2026, 10, 9, 10, 30, tzinfo=UTC)


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


def _signal(placement: Placement, **fields: object) -> Signal:
    values: dict[str, object] = {
        "placement_id": placement.id,
        "source_kind": SourceKind.SESSION.value,
        "source_id": uuid.uuid4(),
        "category": SignalCategory.ISSUE.value,
        "dimension": Dimension.TECHNICAL.value,
        "polarity": Polarity.NEGATIVE.value,
        "severity": 2,
        "confidence": 0.8,
        "quote": "I still can't get into the staging cluster",
        "speaker_role": SpeakerRole.CONSULTANT.value,
        "occurred_at": NOW,
        "offset_ms": 61_000,
    }
    values.update(fields)
    return Signal(**values)


def _action(placement: Placement, **fields: object) -> Action:
    values: dict[str, object] = {
        "placement_id": placement.id,
        "source_kind": SourceKind.SESSION.value,
        "source_id": uuid.uuid4(),
        "owner_role": SpeakerRole.SME.value,
        "description": "Raise the access request with the client's platform team",
        "quote": "I'll chase the platform team for your access",
    }
    values.update(fields)
    return Action(**values)


class TestDefaults:
    async def test_new_issue_is_open_seen_once(self, db_session: AsyncSession) -> None:
        placement = await _placement(db_session)
        issue = Issue(
            placement_id=placement.id,
            topic="No access to the staging cluster",
            first_seen_at=NOW,
            last_seen_at=NOW,
        )
        db_session.add(issue)
        await db_session.flush()
        await db_session.refresh(issue)

        assert issue.status == IssueStatus.OPEN.value
        assert issue.occurrence_count == 1
        assert issue.resolved_at is None

    async def test_new_action_is_open_with_no_owner_user(
        self, db_session: AsyncSession
    ) -> None:
        action = _action(await _placement(db_session))
        db_session.add(action)
        await db_session.flush()
        await db_session.refresh(action)

        assert action.status == ActionStatus.OPEN.value
        assert action.owner_user_id is None
        assert action.closed_at is None

    async def test_signal_stores_without_an_embedding(
        self, db_session: AsyncSession
    ) -> None:
        signal = _signal(await _placement(db_session))
        db_session.add(signal)
        await db_session.flush()
        await db_session.refresh(signal)

        assert signal.embedding is None


class TestSignalConstraints:
    @pytest.mark.parametrize(
        ("field", "value"),
        [
            ("source_kind", "email"),
            ("category", "summary"),
            ("dimension", "finance"),
            ("polarity", "mixed"),
            ("speaker_role", "client"),
            ("severity", 0),
            ("severity", 4),
            ("confidence", -0.1),
            ("confidence", 1.1),
        ],
    )
    async def test_signal_value_outside_its_set_is_refused(
        self, db_session: AsyncSession, field: str, value: object
    ) -> None:
        db_session.add(_signal(await _placement(db_session), **{field: value}))
        with pytest.raises(IntegrityError):
            await db_session.flush()

    async def test_signal_keeps_its_row_when_its_issue_is_deleted(
        self, db_session: AsyncSession
    ) -> None:
        placement = await _placement(db_session)
        issue = Issue(
            placement_id=placement.id,
            topic="No access",
            first_seen_at=NOW,
            last_seen_at=NOW,
        )
        db_session.add(issue)
        await db_session.flush()
        signal = _signal(placement, issue_id=issue.id)
        db_session.add(signal)
        await db_session.flush()

        await db_session.delete(issue)
        await db_session.flush()
        await db_session.refresh(signal)

        assert signal.issue_id is None


class TestIssueAndActionConstraints:
    async def test_issue_status_outside_its_set_is_refused(
        self, db_session: AsyncSession
    ) -> None:
        placement = await _placement(db_session)
        db_session.add(
            Issue(
                placement_id=placement.id,
                topic="x",
                first_seen_at=NOW,
                last_seen_at=NOW,
                status="parked",
            )
        )
        with pytest.raises(IntegrityError):
            await db_session.flush()

    @pytest.mark.parametrize(
        ("field", "value"),
        [
            ("source_kind", "email"),
            ("owner_role", "client"),
            ("status", "cancelled"),
        ],
    )
    async def test_action_value_outside_its_set_is_refused(
        self, db_session: AsyncSession, field: str, value: str
    ) -> None:
        db_session.add(_action(await _placement(db_session), **{field: value}))
        with pytest.raises(IntegrityError):
            await db_session.flush()

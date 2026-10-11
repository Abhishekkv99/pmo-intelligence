"""The risk board and the placement health page, against Postgres.

Pinned here: the board lists the active placements in the caller's scope in
board order (red first, then falling, then lowest overall, then name; not
scored last) and writes no access log; an SME's board and page are the
technical view (no overall, level, overall trend, flags, other dimensions or
contract fields) and their board is ordered by Technical score; the page
answers 404 outside scope exactly as for a missing placement, writes an
``access_log`` row, resolves evidence to quotes, and lists the history,
flags, calls, open issues, actions and the consultant's other placements in
the reader's scope.
"""

import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.access_log import AccessLog
from app.models.enums import Role
from app.models.health import HealthSnapshot, RiskFlag
from app.models.register import Client, Consultant, Placement, Project
from app.models.session import Session
from app.models.signal import Action, Issue, Signal
from app.models.user import User
from app.services import health_view
from app.services.auth_service import AuthService

# 13:00 in London on Tuesday 20 October 2026
NOW = datetime(2026, 10, 20, 12, 0, tzinfo=UTC)
START = date(2026, 9, 1)  # 49 days before NOW: 7 weeks in


def _bearer(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {AuthService.create_access_token(user.id)}"}


@pytest.fixture(autouse=True)
def _fixed_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(health_view, "_utc_now", lambda: NOW)


class World:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def user(self, role: Role, name: str) -> User:
        user = User(
            email=f"{name.lower()}-{uuid.uuid4()}@example.com",
            full_name=name,
            role=role.value,
        )
        self.db.add(user)
        await self.db.flush()
        return user

    async def consultant(self, name: str) -> Consultant:
        consultant = Consultant(full_name=name)
        self.db.add(consultant)
        await self.db.flush()
        return consultant

    async def placement(
        self,
        consultant: str | Consultant,
        *,
        client: str = "Acme",
        ps: User | None = None,
        sme: User | None = None,
        cdm: User | None = None,
        status: str = "active",
        start_date: date = START,
    ) -> Placement:
        if isinstance(consultant, str):
            consultant = await self.consultant(consultant)
        if cdm is not None:
            consultant.cdm_user_id = cdm.id
        row = Client(name=client, normalized_name=f"{client.lower()} {uuid.uuid4()}")
        self.db.add(row)
        await self.db.flush()
        project = Project(
            client_id=row.id,
            name="Data platform",
            client_manager_name="Morgan",
        )
        self.db.add(project)
        await self.db.flush()
        placement = Placement(
            consultant_id=consultant.id,
            project_id=project.id,
            start_date=start_date,
            expected_end_date=date(2027, 3, 31),
            extension_status="due",
            rate_band="B",
            stack="DS",
            ps_user_id=ps.id if ps else None,
            sme_user_id=sme.id if sme else None,
            status=status,
            ended_reason="Client cut the budget" if status != "active" else None,
        )
        self.db.add(placement)
        await self.db.flush()
        return placement

    async def snapshot(
        self, placement: Placement, *, computed_at: datetime = NOW, **fields: Any
    ) -> HealthSnapshot:
        values: dict[str, Any] = {
            "placement_id": placement.id,
            "computed_at": computed_at,
            "reason": "call",
            "scored": True,
            "delivery": 6.0,
            "technical": 7.0,
            "relationship": 6.5,
            "engagement": 7.0,
            "onboarding": 7.0,
            "communication": 7.0,
            "overall": 6.6,
            "trend": "flat",
            "trend_delta": 0.1,
            "technical_trend": "up",
            "technical_trend_delta": 0.7,
            "risk_level": "amber",
            "signal_count": 3,
            "weights_version": "v1",
            "evidence": {},
        }
        values.update(fields)
        snapshot = HealthSnapshot(**values)
        self.db.add(snapshot)
        await self.db.flush()
        return snapshot

    async def not_scored(self, placement: Placement) -> HealthSnapshot:
        return await self.snapshot(
            placement,
            scored=False,
            **dict.fromkeys(
                [
                    "delivery",
                    "technical",
                    "relationship",
                    "engagement",
                    "onboarding",
                    "communication",
                    "overall",
                    "trend",
                    "trend_delta",
                    "technical_trend",
                    "technical_trend_delta",
                    "risk_level",
                ]
            ),
            signal_count=0,
        )

    async def session(
        self,
        placement: Placement,
        held_at: datetime,
        *,
        status: str = "completed",
    ) -> Session:
        session = Session(
            placement_id=placement.id,
            held_at=held_at,
            source="upload",
            status=status,
            kind="check_in",
            duration_seconds=1800.0,
        )
        self.db.add(session)
        await self.db.flush()
        return session

    async def signal(
        self,
        placement: Placement,
        session: Session,
        quote: str,
        *,
        dimension: str = "technical",
        offset_ms: int = 1000,
        **fields: Any,
    ) -> Signal:
        values: dict[str, Any] = {
            "placement_id": placement.id,
            "source_kind": "session",
            "source_id": session.id,
            "category": "issue",
            "dimension": dimension,
            "polarity": "negative",
            "severity": 2,
            "confidence": 0.9,
            "quote": quote,
            "speaker_role": "consultant",
            "occurred_at": session.held_at + timedelta(milliseconds=offset_ms),
            "offset_ms": offset_ms,
        }
        values.update(fields)
        signal = Signal(**values)
        self.db.add(signal)
        await self.db.flush()
        return signal

    async def flag(
        self,
        placement: Placement,
        trigger: str = "client_dissatisfaction",
        *,
        severity: str = "critical",
        evidence: list[uuid.UUID] | None = None,
        closed: bool = False,
        opened_days_ago: int = 2,
    ) -> RiskFlag:
        flag = RiskFlag(
            placement_id=placement.id,
            trigger=trigger,
            severity=severity,
            opened_at=NOW - timedelta(days=opened_days_ago),
            evidence_signal_ids=evidence or [],
            closed_at=NOW - timedelta(days=1) if closed else None,
        )
        self.db.add(flag)
        await self.db.flush()
        return flag

    async def action(
        self,
        placement: Placement,
        description: str,
        *,
        due: date | None = None,
        status: str = "open",
        closed_at: datetime | None = None,
    ) -> Action:
        action = Action(
            placement_id=placement.id,
            source_kind="session",
            source_id=uuid.uuid4(),
            owner_role="consultant",
            description=description,
            quote="I will do it.",
            due_date=due,
            status=status,
            closed_at=closed_at,
        )
        self.db.add(action)
        await self.db.flush()
        return action


@pytest.fixture
def world(db_session: AsyncSession) -> World:
    return World(db_session)


async def _access_rows(db: AsyncSession) -> list[AccessLog]:
    return list((await db.execute(select(AccessLog))).scalars().all())


def _names(body: list[dict[str, Any]]) -> list[str]:
    return [row["consultant"]["name"] for row in body]


class TestRiskBoard:
    async def test_a_manager_sees_every_active_placement_in_board_order(
        self, manager_client: AsyncClient, world: World, db_session: AsyncSession
    ) -> None:
        # Red before amber before green; within red, falling before flat, and
        # the lower overall first; not scored and never recomputed last, by name.
        cases = [
            ("Zed Green", {"risk_level": "green", "overall": 7.8, "trend": "up"}),
            ("Yan Amber", {"risk_level": "amber", "overall": 6.0, "trend": "down"}),
            ("Xia Flat", {"risk_level": "red", "overall": 4.0, "trend": "flat"}),
            ("Ann Down", {"risk_level": "red", "overall": 4.5, "trend": "down"}),
            ("Bob Down", {"risk_level": "red", "overall": 3.9, "trend": "down"}),
            ("Cal Fresh", {"risk_level": "red", "overall": 3.0, "trend": None}),
        ]
        for name, fields in cases:
            await world.snapshot(await world.placement(name), **fields)
        await world.not_scored(await world.placement("Wes Unscored"))
        await world.placement("Abe Never")
        ended = await world.placement("Old Ended", status="ended")
        await world.snapshot(ended, risk_level="red", overall=2.0, trend="down")

        response = await manager_client.get("/api/v1/risk-board")

        assert response.status_code == 200
        body = response.json()
        assert _names(body) == [
            "Bob Down",
            "Ann Down",
            "Xia Flat",
            "Cal Fresh",
            "Yan Amber",
            "Zed Green",
            "Abe Never",
            "Wes Unscored",
        ]
        assert {row["view"] for row in body} == {"full"}
        never = body[6]
        assert never["scored"] is False
        assert never["computed_at"] is None
        assert never["overall"] is None
        assert await _access_rows(db_session) == []

    async def test_a_row_carries_scores_flags_weeks_last_call_and_next_action(
        self, manager_client: AsyncClient, world: World
    ) -> None:
        ps = await world.user(Role.PS, "Pat")
        cdm = await world.user(Role.CDM, "Lee")
        placement = await world.placement("Priya Shah", ps=ps, cdm=cdm)
        await world.snapshot(placement, computed_at=NOW - timedelta(days=3))
        latest = await world.snapshot(
            placement, risk_level="red", overall=4.6, trend="down", trend_delta=-1.2
        )
        flag = await world.flag(placement)
        await world.flag(placement, "contract_horizon", severity="high", closed=True)
        # The last completed call was 15 October; a later failed one counts not.
        await world.session(placement, datetime(2026, 10, 15, 9, 0, tzinfo=UTC))
        await world.session(
            placement, datetime(2026, 10, 18, 9, 0, tzinfo=UTC), status="failed"
        )
        overdue = await world.action(
            placement, "Send the report", due=date(2026, 10, 18)
        )
        await world.action(placement, "Book the review", due=date(2026, 10, 25))
        await world.action(placement, "Ask about access")
        await world.action(
            placement,
            "Old thing",
            due=date(2026, 10, 1),
            status="done",
            closed_at=NOW - timedelta(days=5),
        )

        response = await manager_client.get("/api/v1/risk-board")

        [row] = response.json()
        assert row["placement_id"] == str(placement.id)
        assert row["client"]["name"] == "Acme"
        assert row["project"]["name"] == "Data platform"
        assert row["ps"]["full_name"] == "Pat"
        assert row["cdm"]["full_name"] == "Lee"
        assert row["stack"] == "DS"
        assert row["start_date"] == "2026-09-01"
        assert row["weeks_in"] == 7
        assert row["scored"] is True
        assert row["computed_at"] == latest.computed_at.isoformat().replace(
            "+00:00", "Z"
        )
        assert row["overall"] == 4.6
        assert row["risk_level"] == "red"
        assert row["trend"] == "down"
        assert row["trend_delta"] == -1.2
        assert row["technical"] == 7.0
        assert row["technical_trend"] == "up"
        assert [f["id"] for f in row["open_flags"]] == [str(flag.id)]
        assert row["open_flags"][0]["trigger"] == "client_dissatisfaction"
        assert row["open_flags"][0]["severity"] == "critical"
        assert row["days_since_last_call"] == 5
        assert row["next_action"] == {
            "id": str(overdue.id),
            "description": "Send the report",
            "owner_role": "consultant",
            "due_date": "2026-10-18",
        }

    async def test_flags_are_listed_critical_first_then_oldest_then_prd_order(
        self, manager_client: AsyncClient, world: World
    ) -> None:
        placement = await world.placement("Priya Shah")
        # Added in an order that matches none of the rules below.
        await world.flag(
            placement, "contract_horizon", severity="high", opened_days_ago=9
        )
        await world.flag(placement, "intent_to_leave", opened_days_ago=1)
        await world.flag(placement, "client_dissatisfaction", opened_days_ago=1)
        await world.flag(
            placement, "downward_trend", severity="high", opened_days_ago=1
        )

        [row] = (await manager_client.get("/api/v1/risk-board")).json()
        page = await manager_client.get(f"/api/v1/placements/{placement.id}/health")

        # Critical before high; the older high first; the two critical flags
        # opened together in the PRD's trigger order.
        expected = [
            "client_dissatisfaction",
            "intent_to_leave",
            "contract_horizon",
            "downward_trend",
        ]
        assert [f["trigger"] for f in row["open_flags"]] == expected
        assert [f["trigger"] for f in page.json()["open_flags"]] == expected

    async def test_a_row_without_calls_or_dated_actions_has_none(
        self, manager_client: AsyncClient, world: World
    ) -> None:
        placement = await world.placement("Priya Shah")
        await world.action(placement, "Ask about access")

        [row] = (await manager_client.get("/api/v1/risk-board")).json()

        assert row["last_call_at"] is None
        assert row["days_since_last_call"] is None
        assert row["next_action"] is None

    @pytest.mark.parametrize("named_as", ["ps", "cdm"])
    async def test_a_named_role_sees_only_the_placements_naming_them(
        self, manager_client: AsyncClient, world: World, named_as: str
    ) -> None:
        role = {"ps": Role.PS, "cdm": Role.CDM}[named_as]
        person = await world.user(role, "Named")
        mine = await world.placement("Priya Shah", **{named_as: person})
        await world.snapshot(mine)
        flag = await world.flag(mine)
        await world.placement("Ann Brooks")

        response = await manager_client.get(
            "/api/v1/risk-board", headers=_bearer(person)
        )

        [row] = response.json()
        assert row["placement_id"] == str(mine.id)
        assert row["view"] == "full"
        assert row["overall"] == 6.6
        assert [f["id"] for f in row["open_flags"]] == [str(flag.id)]

    async def test_an_sme_sees_the_technical_view_ordered_by_technical_score(
        self, manager_client: AsyncClient, world: World
    ) -> None:
        sme = await world.user(Role.SME, "Sam")
        red = await world.placement("Ann Red", sme=sme)
        await world.snapshot(red, risk_level="red", overall=4.0, technical=8.0)
        await world.flag(red)
        green = await world.placement("Zoe Green", sme=sme)
        await world.snapshot(green, risk_level="green", overall=7.5, technical=5.0)
        await world.placement("Abe Never", sme=sme)
        await world.placement("Not Mine")

        response = await manager_client.get("/api/v1/risk-board", headers=_bearer(sme))

        body = response.json()
        # Technical 5.0, then 8.0, then not scored: not the overall's order.
        assert _names(body) == ["Zoe Green", "Ann Red", "Abe Never"]
        for row in body:
            assert row["view"] == "technical"
            assert row["overall"] is None
            assert row["risk_level"] is None
            assert row["trend"] is None
            assert row["trend_delta"] is None
            assert row["open_flags"] == []
        assert [row["technical"] for row in body] == [5.0, 8.0, None]
        assert body[0]["technical_trend"] == "up"
        assert body[0]["technical_trend_delta"] == 0.7


class TestPlacementHealth:
    async def _full_placement(
        self, world: World, ps: User | None = None, sme: User | None = None
    ) -> dict[str, Any]:
        consultant = await world.consultant("Priya Shah")
        placement = await world.placement(consultant, ps=ps, sme=sme)
        other = await world.placement(
            consultant, client="Globex", start_date=date(2026, 1, 5), status="ended"
        )
        older_call = await world.session(
            placement, datetime(2026, 10, 1, 9, 0, tzinfo=UTC)
        )
        newer_call = await world.session(
            placement, datetime(2026, 10, 15, 9, 0, tzinfo=UTC)
        )
        blocker = await world.signal(
            placement, newer_call, "I am still blocked on the VPN."
        )
        unhappy = await world.signal(
            placement,
            newer_call,
            "The client said they are not happy.",
            dimension="delivery",
            category="client",
            severity=3,
            offset_ms=5000,
            indicator="client_dissatisfaction",
        )
        await world.signal(
            placement,
            older_call,
            "The team is great.",
            dimension="relationship",
            polarity="positive",
            category="relationship_engagement",
        )
        evidence = {
            "technical": {
                "signal_count": 1,
                "contributors": [
                    {"signal_id": str(blocker.id), "weight": 0.9, "value": 3.0}
                ],
            },
            "delivery": {
                "signal_count": 1,
                "contributors": [
                    {"signal_id": str(unhappy.id), "weight": 0.9, "value": 1.0}
                ],
            },
        }
        first = await world.snapshot(
            placement, computed_at=NOW - timedelta(days=5), reason="daily"
        )
        latest = await world.snapshot(
            placement,
            risk_level="amber",
            overall=5.8,
            technical=5.1,
            evidence=evidence,
        )
        flag = await world.flag(placement, evidence=[unhappy.id])
        world.db.add_all(
            [
                Issue(
                    placement_id=placement.id,
                    topic="VPN access",
                    first_seen_at=NOW - timedelta(days=19),
                    last_seen_at=NOW - timedelta(days=5),
                    occurrence_count=2,
                ),
                Issue(
                    placement_id=placement.id,
                    topic="Laptop",
                    first_seen_at=NOW - timedelta(days=19),
                    last_seen_at=NOW - timedelta(days=19),
                    status="resolved",
                    resolved_at=NOW - timedelta(days=5),
                ),
            ]
        )
        await world.db.flush()
        await world.action(placement, "Ask about access")
        await world.action(placement, "Book the review", due=date(2026, 10, 25))
        await world.action(placement, "Send the report", due=date(2026, 10, 18))
        await world.action(
            placement,
            "Closed first",
            status="done",
            closed_at=NOW - timedelta(days=9),
        )
        await world.action(
            placement,
            "Closed last",
            status="done",
            closed_at=NOW - timedelta(days=2),
        )
        return {
            "placement": placement,
            "other": other,
            "older_call": older_call,
            "newer_call": newer_call,
            "blocker": blocker,
            "unhappy": unhappy,
            "first": first,
            "latest": latest,
            "flag": flag,
        }

    async def test_a_manager_reads_the_full_page_and_it_is_logged(
        self,
        manager_client: AsyncClient,
        world: World,
        db_session: AsyncSession,
        test_manager: User,
    ) -> None:
        ps = await world.user(Role.PS, "Pat")
        made = await self._full_placement(world, ps=ps)
        placement: Placement = made["placement"]
        path = f"/api/v1/placements/{placement.id}/health"

        response = await manager_client.get(path)

        assert response.status_code == 200
        body = response.json()
        assert body["view"] == "full"
        assert body["consultant"]["name"] == "Priya Shah"
        assert body["weeks_in"] == 7
        register = body["register_fields"]
        assert register["extension_status"] == "due"
        assert register["rate_band"] == "B"
        assert register["stack"] == "DS"
        assert register["client_manager_name"] == "Morgan"
        assert register["ps"]["full_name"] == "Pat"

        latest = body["latest"]
        assert latest["overall"] == 5.8
        assert latest["risk_level"] == "amber"
        assert latest["scores"]["delivery"] == 6.0
        assert latest["scores"]["technical"] == 5.1
        assert latest["signal_count"] == 3
        by_dimension = {e["dimension"]: e for e in latest["evidence"]}
        assert set(by_dimension) == {"technical", "delivery"}
        delivery = by_dimension["delivery"]["contributors"][0]
        assert delivery["signal"]["quote"] == "The client said they are not happy."
        assert delivery["signal"]["source_id"] == str(made["newer_call"].id)
        assert delivery["signal"]["offset_ms"] == 5000
        assert delivery["signal"]["indicator"] == "client_dissatisfaction"
        assert delivery["weight"] == 0.9
        assert delivery["value"] == 1.0

        assert [p["reason"] for p in body["history"]] == ["daily", "call"]
        assert body["history"][1]["overall"] == 5.8

        [flag] = body["open_flags"]
        assert flag["id"] == str(made["flag"].id)
        assert [s["quote"] for s in flag["evidence"]] == [
            "The client said they are not happy."
        ]

        assert [s["id"] for s in body["sessions"]] == [
            str(made["newer_call"].id),
            str(made["older_call"].id),
        ]
        assert [s["signal_count"] for s in body["sessions"]] == [2, 1]
        assert [i["topic"] for i in body["open_issues"]] == ["VPN access"]
        assert [a["description"] for a in body["actions"]] == [
            "Send the report",
            "Book the review",
            "Ask about access",
            "Closed last",
            "Closed first",
        ]
        assert [p["id"] for p in body["other_placements"]] == [str(made["other"].id)]
        assert body["other_placements"][0]["client"]["name"] == "Globex"
        assert body["other_placements"][0]["status"] == "ended"
        # The v1 configuration's RAG thresholds, for the page's bands.
        assert body["thresholds"] == {"green_from": 7.0, "amber_from": 5.0}

        rows = await _access_rows(db_session)
        assert [(r.user_id, r.placement_id, r.route) for r in rows] == [
            (test_manager.id, placement.id, path)
        ]

    async def test_an_sme_reads_the_technical_view(
        self, manager_client: AsyncClient, world: World, db_session: AsyncSession
    ) -> None:
        sme = await world.user(Role.SME, "Sam")
        made = await self._full_placement(world, sme=sme)
        placement: Placement = made["placement"]

        response = await manager_client.get(
            f"/api/v1/placements/{placement.id}/health", headers=_bearer(sme)
        )

        assert response.status_code == 200
        body = response.json()
        assert body["view"] == "technical"
        register = body["register_fields"]
        assert register["extension_status"] is None
        assert register["rate_band"] is None
        assert register["ended_reason"] is None
        assert register["stack"] == "DS"
        assert register["start_date"] == "2026-09-01"
        assert register["sme"]["full_name"] == "Sam"

        latest = body["latest"]
        assert latest["scores"] == {
            "delivery": None,
            "technical": 5.1,
            "relationship": None,
            "engagement": None,
            "onboarding": None,
            "communication": None,
        }
        assert latest["overall"] is None
        assert latest["risk_level"] is None
        assert latest["trend"] is None
        assert latest["trend_delta"] is None
        assert latest["signal_count"] is None
        assert latest["technical_trend"] == "up"
        assert [e["dimension"] for e in latest["evidence"]] == ["technical"]
        assert latest["evidence"][0]["contributors"][0]["signal"]["quote"] == (
            "I am still blocked on the VPN."
        )
        for point in body["history"]:
            assert point["overall"] is None
            assert point["risk_level"] is None
            assert point["trend"] is None
            assert point["scores"]["delivery"] is None
            assert point["scores"]["technical"] is not None
        assert body["open_flags"] == []
        # Technical signals only: the newer call has one, the older none.
        assert [s["signal_count"] for s in body["sessions"]] == [1, 0]
        # The SME is not named on the consultant's other placement.
        assert body["other_placements"] == []
        # Configuration, not data about the placement: given in every view.
        assert body["thresholds"] == {"green_from": 7.0, "amber_from": 5.0}
        assert len(await _access_rows(db_session)) == 1

    async def test_other_placements_are_cut_to_the_readers_scope(
        self, manager_client: AsyncClient, world: World
    ) -> None:
        ps = await world.user(Role.PS, "Pat")
        consultant = await world.consultant("Priya Shah")
        mine = await world.placement(consultant, ps=ps)
        also_mine = await world.placement(
            consultant, ps=ps, client="Globex", start_date=date(2026, 3, 1)
        )
        await world.placement(consultant, client="Initech", start_date=date(2025, 6, 1))

        response = await manager_client.get(
            f"/api/v1/placements/{mine.id}/health", headers=_bearer(ps)
        )

        assert [p["id"] for p in response.json()["other_placements"]] == [
            str(also_mine.id)
        ]

    async def test_a_placement_never_recomputed_has_no_latest(
        self, manager_client: AsyncClient, world: World
    ) -> None:
        placement = await world.placement("Priya Shah")

        response = await manager_client.get(f"/api/v1/placements/{placement.id}/health")

        body = response.json()
        assert body["latest"] is None
        assert body["history"] == []
        assert body["open_flags"] == []
        assert body["sessions"] == []

    async def test_outside_scope_is_a_404_like_a_missing_placement_and_not_logged(
        self, manager_client: AsyncClient, world: World, db_session: AsyncSession
    ) -> None:
        stranger = await world.user(Role.SME, "Stranger")
        placement = await world.placement("Priya Shah")
        missing = uuid.uuid4()

        denied = await manager_client.get(
            f"/api/v1/placements/{placement.id}/health", headers=_bearer(stranger)
        )
        absent = await manager_client.get(
            f"/api/v1/placements/{missing}/health", headers=_bearer(stranger)
        )

        assert denied.status_code == absent.status_code == 404
        assert denied.json()["detail"] == absent.json()["detail"].replace(
            str(missing), str(placement.id)
        )
        assert await _access_rows(db_session) == []

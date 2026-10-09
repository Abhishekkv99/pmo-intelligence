"""Write one analysed session for the end-to-end tests, and print its ids.

The compose stack has no AssemblyAI or Azure OpenAI key, so no session can be
analysed there for real. This writes what an analysed call leaves behind (a
placement, a completed session with its recording, transcript, signals, an
issue, actions and costs) so the session page can be tested end to end. Every
quote is found in the transcript, as the pipeline would require.

Development and CI only: it refuses to run unless local sign-in is enabled
and storage is local files, which is never the case on staging or production.

With ``--failed`` it writes instead a session that failed before it was
transcribed (its recording stored, nothing else), for testing retry: a retry
runs the real job, which fails again at transcription on a stack without an
AssemblyAI key.

Usage (in the backend container):
    python -m app.cli.seed_e2e_session --run abc123 [--failed]

Prints one JSON line: ``{"session_id", "placement_id", "consultant"}``.
"""

import argparse
import asyncio
import json
import sys
import uuid
from datetime import UTC, date, datetime, timedelta

from app.config import settings
from app.db.session import async_session_factory
from app.models.enums import (
    ActionStatus,
    IssueStatus,
    SessionKind,
    SessionSource,
    SessionStatus,
    SourceKind,
)
from app.models.processing_cost import ProcessingCost
from app.models.register import Client, Consultant, Placement, Project
from app.models.session import Session, SessionTranscript
from app.models.signal import Action, Issue, Signal
from app.services.register_service import normalize_name
from app.services.storage import get_storage_backend
from app.services.upload_service import session_media_key

HELD_AT = datetime(2026, 10, 1, 9, 0, tzinfo=UTC)
SEEDED_FAILURE = "Seeded failure for the end-to-end tests; retry it"
# The first bytes of a WebM file; enough for the media route to serve it.
RECORDING = b"\x1a\x45\xdf\xa3" + b"\x00" * 2048

UTTERANCES = [
    ("A", "Thanks for joining, how is the first month going?", 0, 4_000),
    ("B", "I am still blocked on VPN access to the client network.", 5_000, 9_000),
    ("A", "I will chase the client's IT team for the VPN today.", 10_000, 14_000),
    ("B", "The team lead has been really supportive so far.", 15_000, 19_000),
]
# Each found in the transcript above, at the offset used below.
ISSUE_QUOTE = "still blocked on VPN access to the client network"
RELATIONSHIP_QUOTE = "The team lead has been really supportive so far."
ACTION_QUOTE = "I will chase the client's IT team for the VPN today."


def _refuse_outside_development() -> str | None:
    if not settings.local_auth_enabled:
        return "Refused: local sign-in is off, so this is not a development stack"
    if settings.storage_backend == "s3":
        return "Refused: storage is S3, so this is not a development stack"
    return None


async def seed(run: str, *, failed: bool = False) -> dict[str, str]:
    async with async_session_factory() as db:
        client_name = f"E2E Session Client {run}"
        client = Client(name=client_name, normalized_name=normalize_name(client_name))
        consultant = Consultant(full_name=f"Esme {run}")
        db.add_all([client, consultant])
        await db.flush()
        project = Project(
            client_id=client.id, name="Data platform", client_manager_name="Dana Lee"
        )
        db.add(project)
        await db.flush()
        placement = Placement(
            consultant_id=consultant.id,
            project_id=project.id,
            start_date=date(2026, 9, 1),
        )
        db.add(placement)
        await db.flush()

        session = Session(
            id=uuid.uuid4(),
            placement_id=placement.id,
            kind=SessionKind.TECHNICAL.value,
            held_at=HELD_AT,
            duration_seconds=1_200.0,
            source=SessionSource.UPLOAD.value,
            original_filename="Recording 2026-10-01 10-00-00.webm",
            status=SessionStatus.COMPLETED.value,
            node_errors=[{"node": "client_signals", "error": "Timed out after 240 s"}],
        )
        if failed:
            session.status = SessionStatus.FAILED.value
            session.error_message = SEEDED_FAILURE
            session.duration_seconds = None
            session.node_errors = []
        session.recording_key = await get_storage_backend().upload(
            session_media_key(session.id, session.original_filename or "call.webm"),
            RECORDING,
        )
        db.add(session)
        await db.flush()
        if failed:
            await db.commit()
            return _ids(session, placement, consultant)

        db.add(
            SessionTranscript(
                session_id=session.id,
                full_text=" ".join(text for _, text, _, _ in UTTERANCES),
                utterances=[
                    {
                        "speaker": speaker,
                        "text": text,
                        "start_ms": start,
                        "end_ms": end,
                        "confidence": 0.95,
                    }
                    for speaker, text, start, end in UTTERANCES
                ],
                speaker_roles={
                    "A": {"role": "sme", "name": "Sam"},
                    "B": {"role": "consultant", "name": consultant.full_name},
                },
                summary=(
                    "The consultant is still blocked on VPN access; the SME will "
                    "chase the client's IT team. The team lead is supportive."
                ),
                session_class=SessionKind.TECHNICAL.value,
                project_phase="first month",
            )
        )
        issue = Issue(
            placement_id=placement.id,
            topic="VPN access to the client network",
            first_seen_at=HELD_AT,
            last_seen_at=HELD_AT,
            status=IssueStatus.OPEN.value,
        )
        db.add(issue)
        await db.flush()

        def signal(**fields: object) -> Signal:
            offset = int(str(fields["offset_ms"]))
            return Signal(
                placement_id=placement.id,
                source_kind=SourceKind.SESSION.value,
                source_id=session.id,
                speaker_role="consultant",
                occurred_at=HELD_AT + timedelta(milliseconds=offset),
                **fields,
            )

        db.add_all(
            [
                signal(
                    category="issue",
                    dimension="onboarding",
                    polarity="negative",
                    severity=2,
                    confidence=0.9,
                    quote=ISSUE_QUOTE,
                    note="Access still missing a month in.",
                    offset_ms=5_000,
                    issue_id=issue.id,
                ),
                signal(
                    category="relationship_engagement",
                    dimension="relationship",
                    polarity="positive",
                    severity=1,
                    confidence=0.8,
                    quote=RELATIONSHIP_QUOTE,
                    note="Good relationship with the team lead.",
                    offset_ms=15_000,
                ),
                Action(
                    placement_id=placement.id,
                    source_kind=SourceKind.SESSION.value,
                    source_id=session.id,
                    owner_role="sme",
                    description="Chase the client's IT team for VPN access",
                    quote=ACTION_QUOTE,
                    offset_ms=10_000,
                    due_text="today",
                    due_date=date(2026, 10, 1),
                    status=ActionStatus.OPEN.value,
                ),
                ProcessingCost(
                    session_id=session.id,
                    service="assemblyai",
                    operation="transcription",
                    amount_usd=0.0767,
                ),
                ProcessingCost(
                    session_id=session.id,
                    service="azure_openai",
                    operation="session_pipeline",
                    amount_usd=0.0123,
                ),
            ]
        )
        await db.commit()
        return _ids(session, placement, consultant)


def _ids(
    session: Session, placement: Placement, consultant: Consultant
) -> dict[str, str]:
    return {
        "session_id": str(session.id),
        "placement_id": str(placement.id),
        "consultant": consultant.full_name,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--run", required=True, help="a suffix that makes the names unique"
    )
    parser.add_argument(
        "--failed",
        action="store_true",
        help="a session that failed before transcription, to retry",
    )
    args = parser.parse_args(argv)
    refusal = _refuse_outside_development()
    if refusal:
        print(refusal, file=sys.stderr)
        return 2
    print(json.dumps(asyncio.run(seed(args.run, failed=args.failed))))
    return 0


if __name__ == "__main__":
    sys.exit(main())

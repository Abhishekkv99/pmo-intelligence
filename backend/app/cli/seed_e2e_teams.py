"""Write PMO group chats for the end-to-end tests, and print their titles.

The compose stack has no Graph access, so discovery cannot find a chat there.
This writes what discovery leaves behind for three made-up chats: one whose
title reads but matches no placement (the register has none), one whose
title cannot be read, and one already matched to a placement it creates.
Admin > Teams can then be tested end to end.

Development and CI only: it refuses to run unless local sign-in is enabled
and storage is local files, as the session seed does.

Usage (in the backend container):
    python -m app.cli.seed_e2e_teams --run abc123

Prints one JSON line: ``{"unmatched", "unparsed", "matched"}``, the three
titles.
"""

import argparse
import asyncio
import json
import sys
from datetime import date

from app.cli.seed_e2e_session import _refuse_outside_development
from app.db.session import async_session_factory
from app.models.enums import TeamsChatMatch
from app.models.register import Client, Consultant, Placement, Project
from app.models.teams import TeamsGroup
from app.services.register_service import normalize_name

START = date(2026, 9, 21)
END = date(2027, 3, 21)


def titles(run: str) -> dict[str, str]:
    return {
        "unmatched": f"PRJ ITC DS-Nia {run}-Teams Client {run}-21/9/26-21/3/27",
        "unparsed": f"PRJ ITC - social {run}",
        "matched": (
            f"PRJ ITC QA - Omar {run} - Teams Client {run} - 21/9/2026 - 21/3/2027"
        ),
    }


async def seed(run: str) -> dict[str, str]:
    names = titles(run)
    async with async_session_factory() as db:
        client = Client(
            name=f"Teams Client {run}",
            normalized_name=normalize_name(f"Teams Client {run}"),
        )
        consultant = Consultant(full_name=f"Omar {run}")
        db.add_all([client, consultant])
        await db.flush()
        project = Project(client_id=client.id, name="Platform")
        db.add(project)
        await db.flush()
        placement = Placement(
            consultant_id=consultant.id,
            project_id=project.id,
            start_date=START,
            expected_end_date=END,
            stack="QA",
        )
        db.add(placement)
        await db.flush()

        db.add_all(
            [
                TeamsGroup(
                    graph_chat_id=f"19:e2e-{run}-1@thread.v2",
                    title=names["unmatched"],
                    parsed_stack="DS",
                    parsed_consultant_name=f"Nia {run}",
                    parsed_client_name=f"Teams Client {run}",
                    parsed_start_date=START,
                    parsed_end_date=END,
                    match_status=TeamsChatMatch.UNMATCHED.value,
                ),
                TeamsGroup(
                    graph_chat_id=f"19:e2e-{run}-2@thread.v2",
                    title=names["unparsed"],
                    match_status=TeamsChatMatch.UNPARSED.value,
                    error_message=(
                        "Title not read: expected a start and an end date at "
                        "the end, found 0"
                    ),
                ),
                TeamsGroup(
                    graph_chat_id=f"19:e2e-{run}-3@thread.v2",
                    title=names["matched"],
                    parsed_stack="QA",
                    parsed_consultant_name=f"Omar {run}",
                    parsed_client_name=f"Teams Client {run}",
                    parsed_start_date=START,
                    parsed_end_date=END,
                    match_status=TeamsChatMatch.MATCHED.value,
                    placement_id=placement.id,
                ),
            ]
        )
        await db.commit()
    return names


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--run", required=True, help="A short tag that makes names unique"
    )
    args = parser.parse_args(argv)

    refusal = _refuse_outside_development()
    if refusal:
        print(refusal, file=sys.stderr)
        return 2
    print(json.dumps(asyncio.run(seed(args.run))))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Grant, change or remove a user's role, or list the users.

A role is what lets a person sign in, so this is how a PMO manager lets a
colleague in until the Admin "Users and roles" page exists. Runs as a one-off
ECS task inside the VPC (RDS is private) with the app's ``DATABASE_URL``:
``make user-role ENV=staging EMAIL=... ROLE=...``; see docs/DEPLOYMENT.md.

Usage (inside the task):
    python -m app.cli.user_role --email name@informationtechconsultants.com --role sme
    python -m app.cli.user_role --email name@informationtechconsultants.com --role none
    python -m app.cli.user_role --list
"""

import argparse
import asyncio
import logging
import sys

from app.db.session import async_session_factory
from app.models.enums import Role
from app.services.user_roles import UserRoleService

logger = logging.getLogger("user_role")

NO_ROLE = "none"


async def grant(email: str, role: Role | None) -> int:
    async with async_session_factory() as session:
        try:
            message = await UserRoleService(session).set_role(email, role)
        except ValueError as exc:
            logger.error("%s", exc)
            return 2
        await session.commit()
    logger.info("%s", message)
    return 0


async def list_users() -> int:
    async with async_session_factory() as session:
        users = await UserRoleService(session).list_users()
    logger.info("%d user(s)", len(users))
    for user in users:
        logger.info(
            "%s | %s | %s | %s | %s",
            user.email,
            user.full_name,
            user.role or "no role",
            "active" if user.is_active else "disabled",
            "signed in with Microsoft"
            if user.signed_in_with_microsoft
            else "not signed in yet",
        )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--email", help="the user's email address")
    action.add_argument("--list", action="store_true", help="list every user and role")
    parser.add_argument(
        "--role",
        choices=[role.value for role in Role] + [NO_ROLE],
        help=f"the role to give, or '{NO_ROLE}' to remove it (with --email)",
    )
    args = parser.parse_args(argv)
    if args.email and not args.role:
        parser.error("--email needs --role")
    if args.list and args.role:
        parser.error("--list takes no --role")
    logging.basicConfig(
        level=logging.INFO, format="%(levelname)s %(name)s: %(message)s"
    )

    if args.list:
        return asyncio.run(list_users())
    role = None if args.role == NO_ROLE else Role(args.role)
    return asyncio.run(grant(args.email, role))


if __name__ == "__main__":
    sys.exit(main())

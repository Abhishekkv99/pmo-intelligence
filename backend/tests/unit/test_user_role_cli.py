"""Unit tests for the role CLI's arguments (the service is covered against
Postgres in tests/integration/test_sign_in_access.py)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.cli import user_role
from app.models.enums import Role


class TestMain:
    def test_grants_a_role(self) -> None:
        with patch.object(user_role, "grant", new=AsyncMock(return_value=0)) as grant:
            assert user_role.main(["--email", "a@co.com", "--role", "sme"]) == 0
        grant.assert_awaited_once_with("a@co.com", Role.SME)

    def test_none_removes_the_role(self) -> None:
        with patch.object(user_role, "grant", new=AsyncMock(return_value=0)) as grant:
            user_role.main(["--email", "a@co.com", "--role", "none"])
        grant.assert_awaited_once_with("a@co.com", None)

    def test_lists_users(self) -> None:
        with patch.object(
            user_role, "list_users", new=AsyncMock(return_value=0)
        ) as list_users:
            assert user_role.main(["--list"]) == 0
        list_users.assert_awaited_once_with()

    @pytest.mark.parametrize(
        "argv",
        [
            [],
            ["--email", "a@co.com"],
            ["--email", "a@co.com", "--role", "owner"],
            ["--list", "--role", "sme"],
            ["--list", "--email", "a@co.com", "--role", "sme"],
        ],
    )
    def test_bad_arguments_exit_2(self, argv: list[str]) -> None:
        with pytest.raises(SystemExit) as exc_info:
            user_role.main(argv)
        assert exc_info.value.code == 2

    async def test_grant_rejects_a_bad_address_with_exit_2(self) -> None:
        service = AsyncMock()
        service.set_role.side_effect = ValueError("not an email address: 'x'")
        session = AsyncMock()
        factory = MagicMock()
        factory.return_value.__aenter__ = AsyncMock(return_value=session)
        factory.return_value.__aexit__ = AsyncMock(return_value=False)
        with (
            patch.object(user_role, "async_session_factory", factory),
            patch.object(user_role, "UserRoleService", return_value=service),
        ):
            assert await user_role.grant("x", Role.SME) == 2
        session.commit.assert_not_awaited()

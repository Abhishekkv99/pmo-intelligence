"""Unit tests for the role entitlement rules (app.utils.entitlements)."""

import logging
import uuid
from dataclasses import dataclass

import pytest

from app.config import settings
from app.models.enums import GLOBAL_ROLES, Role
from app.utils.entitlements import (
    PlacementPeople,
    assert_can_read_placement,
    assert_has_role,
    bootstrap_admin_emails,
    can_read_placement,
    elevate_if_bootstrap_admin,
    has_global_scope,
    is_bootstrap_admin,
    list_scope,
)
from app.utils.exceptions import AuthorizationError, NotFoundError

MODULE = "app.utils.entitlements"


@dataclass
class _User:
    id: uuid.UUID
    role: str | None
    email: str = "someone@example.com"


def _user(role: str | None) -> _User:
    return _User(id=uuid.uuid4(), role=role)


def _people(
    ps: uuid.UUID | None = None,
    sme: uuid.UUID | None = None,
    cdm: uuid.UUID | None = None,
) -> PlacementPeople:
    return PlacementPeople(ps_user_id=ps, sme_user_id=sme, cdm_user_id=cdm)


class TestGlobalScope:
    def test_global_roles_are_the_manager_and_admin(self) -> None:
        assert {Role.PMO_MANAGER, Role.ADMIN} == GLOBAL_ROLES

    @pytest.mark.parametrize("role", ["pmo_manager", "admin"])
    def test_global_roles_read_everything(self, role: str) -> None:
        assert has_global_scope(_user(role))
        assert can_read_placement(_user(role), _people())

    @pytest.mark.parametrize("role", ["sme", "cdm", "ps", None, "superuser"])
    def test_other_roles_none_and_unknown_are_not_global(
        self, role: str | None
    ) -> None:
        assert not has_global_scope(_user(role))


class TestPlacementScope:
    @pytest.mark.parametrize("field", ["ps", "sme", "cdm"])
    @pytest.mark.parametrize("role", ["ps", "sme", "cdm"])
    def test_a_scoped_role_reads_a_placement_that_names_them(
        self, role: str, field: str
    ) -> None:
        user = _user(role)
        assert can_read_placement(user, _people(**{field: user.id}))

    @pytest.mark.parametrize("role", ["ps", "sme", "cdm"])
    def test_a_scoped_role_cannot_read_a_placement_naming_others(
        self, role: str
    ) -> None:
        others = _people(ps=uuid.uuid4(), sme=uuid.uuid4(), cdm=uuid.uuid4())
        assert not can_read_placement(_user(role), others)

    def test_no_role_reads_nothing_even_when_named(self) -> None:
        # Fails closed: a row with no role must not read a placement just
        # because someone put its id on it.
        user = _user(None)
        assert not can_read_placement(user, _people(ps=user.id))

    def test_an_unknown_role_reads_nothing_even_when_named(self) -> None:
        user = _user("superuser")
        assert not can_read_placement(user, _people(ps=user.id))

    def test_an_empty_placement_is_visible_only_to_global_roles(self) -> None:
        assert can_read_placement(_user("pmo_manager"), _people())
        assert not can_read_placement(_user("ps"), _people())


class TestAssertCanReadPlacement:
    def test_allowed_returns_none(self) -> None:
        user = _user("ps")
        # Allowed: it returns without raising.
        assert_can_read_placement(user, _people(ps=user.id), uuid.uuid4())

    def test_denied_is_a_404_identical_to_a_missing_row(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        user = _user("ps")
        placement_id = uuid.uuid4()

        with (
            caplog.at_level(logging.WARNING, logger=MODULE),
            pytest.raises(NotFoundError) as denied,
        ):
            assert_can_read_placement(user, _people(), placement_id)

        missing = NotFoundError("Placement", str(placement_id))
        assert denied.value.status_code == 404
        assert denied.value.message == missing.message
        assert f"user_id={user.id}" in caplog.text
        assert "role=ps" in caplog.text
        assert f"resource_id={placement_id}" in caplog.text

    def test_a_sub_resource_names_itself(self) -> None:
        with pytest.raises(NotFoundError, match="Session"):
            assert_can_read_placement(
                _user("ps"), _people(), uuid.uuid4(), resource="Session"
            )


class TestAssertHasRole:
    def test_a_listed_role_passes(self) -> None:
        assert_has_role(_user("admin"), [Role.ADMIN, Role.PMO_MANAGER], "/x")

    @pytest.mark.parametrize("role", ["ps", None])
    def test_another_role_or_none_is_a_403_and_logged(
        self, role: str | None, caplog: pytest.LogCaptureFixture
    ) -> None:
        with (
            caplog.at_level(logging.WARNING, logger=MODULE),
            pytest.raises(AuthorizationError) as denied,
        ):
            assert_has_role(_user(role), [Role.ADMIN], "/api/v1/admin/users")

        assert denied.value.status_code == 403
        assert "resource=/api/v1/admin/users" in caplog.text


class TestBootstrapAdmins:
    def test_emails_are_normalised(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(settings, "bootstrap_admin_emails", " A@x.com ,, b@Y.com ")
        assert bootstrap_admin_emails() == {"a@x.com", "b@y.com"}
        assert is_bootstrap_admin("B@y.COM")
        assert not is_bootstrap_admin("c@x.com")

    def test_a_listed_user_without_a_role_becomes_pmo_manager(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        monkeypatch.setattr(settings, "bootstrap_admin_emails", "boss@example.com")
        user = _User(id=uuid.uuid4(), role=None, email="Boss@Example.com")

        with caplog.at_level(logging.INFO, logger=MODULE):
            changed = elevate_if_bootstrap_admin(user)  # type: ignore[arg-type]

        assert changed is True
        assert user.role == "pmo_manager"
        assert "Bootstrap admin elevated" in caplog.text

    def test_a_listed_scoped_role_is_raised(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "bootstrap_admin_emails", "lead@example.com")
        user = _User(id=uuid.uuid4(), role="cdm", email="lead@example.com")

        assert elevate_if_bootstrap_admin(user) is True  # type: ignore[arg-type]
        assert user.role == "pmo_manager"

    @pytest.mark.parametrize("role", ["pmo_manager", "admin"])
    def test_a_listed_global_role_is_left_alone(
        self, role: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "bootstrap_admin_emails", "ops@example.com")
        user = _User(id=uuid.uuid4(), role=role, email="ops@example.com")

        assert elevate_if_bootstrap_admin(user) is False  # type: ignore[arg-type]
        assert user.role == role

    def test_an_unlisted_user_is_never_touched(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "bootstrap_admin_emails", "boss@example.com")
        user = _User(id=uuid.uuid4(), role="sme", email="other@example.com")

        assert elevate_if_bootstrap_admin(user) is False  # type: ignore[arg-type]
        assert user.role == "sme"


class TestListScope:
    @pytest.mark.parametrize("role", sorted(GLOBAL_ROLES))
    def test_a_global_role_lists_everything(self, role: str) -> None:
        scope = list_scope(_user(role))
        assert scope.everything and not scope.nothing

    @pytest.mark.parametrize("role", [Role.PS.value, Role.SME.value, Role.CDM.value])
    def test_a_named_role_lists_the_placements_naming_them(self, role: str) -> None:
        user = _user(role)
        scope = list_scope(user)
        assert not scope.everything
        assert scope.named_user_id == user.id

    @pytest.mark.parametrize("role", [None, "", "superuser"])
    def test_no_role_or_an_unknown_one_lists_nothing(self, role: str | None) -> None:
        assert list_scope(_user(role)).nothing

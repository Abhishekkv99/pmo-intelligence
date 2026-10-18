"""Every API route must carry an entitlement guard, or be listed here as public
or self-scoped with a reason.

"The check happens in exactly one place" is true the day it ships and quietly
false the first time someone adds a route. This test walks the live app and
turns that into a red build naming the route (docs/PRD.md: "a coverage test
fails the build for any route without it"). Adding a route means either
declaring a guard dependency on it (``require_roles(...)``,
``require_placement_scope``, ``require_logged_placement_scope``,
``require_session_scope``, ``require_logged_session_scope``) or adding it to
one of the explicit sets below.

A route addressed by a placement id must carry a *placement-scope* guard
specifically: a role check alone would let a PS read a placement that does
not name them. A route addressed by a recording, recordings folder or user id
must carry a *role* guard: those rows belong to no placement, so only the
global roles may reach them. A route addressed by a session id must carry a
*session-scope* guard, which checks the session's placement.

A route the browser reaches without the Bearer token (the audio player's
source) is *token-scoped*: listed below, it must carry a guard marked as a
token guard, which accepts only a short-lived token naming the one row.
"""

import pytest
from fastapi.dependencies.models import Dependant
from fastapi.routing import APIRoute

from app.dependencies import (
    GUARD_ATTR,
    TOKEN_GUARD_ATTR,
    get_current_user,
    require_logged_placement_scope,
    require_logged_session_scope,
    require_media_token,
    require_placement_scope,
    require_roles,
    require_session_scope,
)
from app.main import app
from app.models.enums import Role

PLACEMENT_GUARDS = {require_placement_scope, require_logged_placement_scope}
SESSION_GUARDS = {require_session_scope, require_logged_session_scope}

# Path parameters of rows outside any placement: global roles only.
ROLE_ONLY_IDS = ("{recording_id}", "{folder_id}", "{user_id}", "{chat_id}")

# Reachable without a user at all. Each entry is a decision, not an oversight.
PUBLIC = {
    ("GET", "/api/v1/health"),
    ("POST", "/api/v1/auth/register"),
    ("POST", "/api/v1/auth/login"),
    ("POST", "/api/v1/auth/refresh"),
    ("GET", "/api/v1/auth/sso/microsoft/config"),
    ("POST", "/api/v1/auth/sso/microsoft/callback"),
}

# Reached without a user, with a short-lived token naming one row instead.
TOKEN_SCOPED = {
    # The audio player's source on local storage (an <audio> tag sends no
    # Bearer token); 404 on S3, where the page gets a presigned URL.
    ("GET", "/api/v1/sessions/{session_id}/media"),
}

# Authenticated, but about the caller alone: nothing to scope.
SELF_SCOPED = {
    ("POST", "/api/v1/auth/logout"),
    ("GET", "/api/v1/auth/me"),
}


def _calls(dependant: Dependant) -> set[object]:
    """Every callable in the dependency tree, decorator-level ones included."""
    found: set[object] = set()
    for sub in dependant.dependencies:
        found.add(sub.call)
        found |= _calls(sub)
    return found


def _is_guard(call: object) -> bool:
    return bool(getattr(call, GUARD_ATTR, False))


def _is_token_guard(call: object) -> bool:
    return _is_guard(call) and bool(getattr(call, TOKEN_GUARD_ATTR, False))


def _is_role_guard(call: object) -> bool:
    return _is_guard(call) and getattr(call, "__qualname__", "").startswith(
        "require_roles."
    )


def _api_routes() -> list[tuple[str, str, APIRoute]]:
    routes = []
    for route in app.routes:
        if isinstance(route, APIRoute) and route.path.startswith("/api/v1/"):
            for method in sorted(route.methods):
                routes.append((method, route.path, route))
    return routes


ROUTES = _api_routes()
KNOWN = {(method, path) for method, path, _ in ROUTES}


class TestExemptListsAreReal:
    """A stale exemption would silently widen the hole it documents."""

    @pytest.mark.parametrize("entry", sorted(PUBLIC | SELF_SCOPED | TOKEN_SCOPED))
    def test_every_listed_route_exists(self, entry: tuple[str, str]) -> None:
        assert entry in KNOWN, f"{entry[0]} {entry[1]} is listed but not registered"

    def test_lists_do_not_overlap(self) -> None:
        assert not (PUBLIC & SELF_SCOPED)
        assert not (PUBLIC & TOKEN_SCOPED)
        assert not (SELF_SCOPED & TOKEN_SCOPED)


class TestGuardsAreMarked:
    def test_the_placement_guards_are_marked(self) -> None:
        assert all(_is_guard(guard) for guard in PLACEMENT_GUARDS)

    def test_the_session_guards_are_marked(self) -> None:
        assert all(_is_guard(guard) for guard in SESSION_GUARDS)

    def test_the_media_token_guard_is_a_token_guard(self) -> None:
        assert _is_token_guard(require_media_token)

    def test_scope_guards_are_not_token_guards(self) -> None:
        assert not any(
            _is_token_guard(guard) for guard in PLACEMENT_GUARDS | SESSION_GUARDS
        )

    def test_get_current_user_is_not_a_guard(self) -> None:
        # Authentication alone is not an entitlement.
        assert not _is_guard(get_current_user)


class TestEveryRouteIsGuarded:
    @pytest.mark.parametrize(
        ("method", "path", "route"),
        ROUTES,
        ids=[f"{m} {p}" for m, p, _ in ROUTES],
    )
    def test_route_carries_an_entitlement(
        self, method: str, path: str, route: APIRoute
    ) -> None:
        key = (method, path)
        calls = _calls(route.dependant)

        if key in PUBLIC:
            assert get_current_user not in calls, (
                f"{key} is listed public but requires auth"
            )
            assert not any(_is_guard(call) for call in calls), (
                f"{key} is listed public but carries a guard"
            )
            return

        if key in TOKEN_SCOPED:
            assert any(_is_token_guard(call) for call in calls), (
                f"{key} is token-scoped and must carry a token guard"
            )
            return

        assert not any(_is_token_guard(call) for call in calls), (
            f"{method} {path} carries a token guard but is not listed token-scoped"
        )

        assert get_current_user in calls, f"{key} must require authentication"

        if key in SELF_SCOPED:
            return

        assert any(_is_guard(call) for call in calls), (
            f"{method} {path} carries no entitlement guard — declare "
            "require_roles(...) / require_placement_scope / "
            "require_logged_placement_scope on it, or add it to an exempt set "
            "above with a reason"
        )

        if "{placement_id}" in path:
            assert calls & PLACEMENT_GUARDS, (
                f"{method} {path} is addressed by a placement id and must carry "
                "a placement-scope guard, not only a role check"
            )

        if "{session_id}" in path:
            assert calls & SESSION_GUARDS, (
                f"{method} {path} is addressed by a session id and must carry "
                "a session-scope guard, not only a role check"
            )

        if any(param in path for param in ROLE_ONLY_IDS):
            assert any(_is_role_guard(call) for call in calls), (
                f"{method} {path} is addressed by an id outside any placement and "
                "must carry require_roles(...)"
            )


class TestRoleGuardDetection:
    def test_require_roles_is_recognised_as_a_role_guard(self) -> None:
        assert _is_role_guard(require_roles(Role.ADMIN))

    def test_placement_guards_are_not_role_guards(self) -> None:
        assert not any(
            _is_role_guard(guard) for guard in PLACEMENT_GUARDS | SESSION_GUARDS
        )

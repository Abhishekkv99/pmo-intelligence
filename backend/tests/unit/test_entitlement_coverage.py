"""Every API route must carry an entitlement guard, or be listed here as public
or self-scoped with a reason.

"The check happens in exactly one place" is true the day it ships and quietly
false the first time someone adds a route. This test walks the live app and
turns that into a red build naming the route (docs/PRD.md: "a coverage test
fails the build for any route without it"). Adding a route means either
declaring a guard dependency on it (``require_roles(...)``,
``require_placement_scope``, ``require_logged_placement_scope``) or adding it
to one of the explicit sets below.

A route addressed by a placement id must carry a *placement-scope* guard
specifically: a role check alone would let a PS read a placement that does
not name them.
"""

import pytest
from fastapi.dependencies.models import Dependant
from fastapi.routing import APIRoute

from app.dependencies import (
    GUARD_ATTR,
    get_current_user,
    require_logged_placement_scope,
    require_placement_scope,
)
from app.main import app

PLACEMENT_GUARDS = {require_placement_scope, require_logged_placement_scope}

# Reachable without a user at all. Each entry is a decision, not an oversight.
PUBLIC = {
    ("GET", "/api/v1/health"),
    ("POST", "/api/v1/auth/register"),
    ("POST", "/api/v1/auth/login"),
    ("POST", "/api/v1/auth/refresh"),
    ("GET", "/api/v1/auth/sso/microsoft/config"),
    ("POST", "/api/v1/auth/sso/microsoft/callback"),
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

    @pytest.mark.parametrize("entry", sorted(PUBLIC | SELF_SCOPED))
    def test_every_listed_route_exists(self, entry: tuple[str, str]) -> None:
        assert entry in KNOWN, f"{entry[0]} {entry[1]} is listed but not registered"

    def test_lists_do_not_overlap(self) -> None:
        assert not (PUBLIC & SELF_SCOPED)


class TestGuardsAreMarked:
    def test_the_placement_guards_are_marked(self) -> None:
        assert all(_is_guard(guard) for guard in PLACEMENT_GUARDS)

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
            return

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

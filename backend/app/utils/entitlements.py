"""Role entitlement: which placements a user may see.

The single owner of the rule. The API layer applies it through dependencies
(``app.dependencies``); nothing else decides who sees what, so there is one
place to read.

Three rules live here:

* **The scope** — a user with a *global* role (``pmo_manager``, ``admin``)
  reads every placement. Any other role reads only the placements that name
  them: as the placement specialist, the SME, or the tech lead of the
  placement's project. A user with no role (``NULL``, the state of a newly
  provisioned SSO account) or an unknown role reads nothing — the check fails
  closed.
* **The status code** — a denied *read* of a resource addressed by id raises
  ``NotFoundError``, byte-identical to a missing row, so a 403 can never
  confirm that a consultant's placement exists. A denied *role-gated*
  operation (an admin page, the queue status) raises ``AuthorizationError``
  (403): the operation names no row, so there is nothing to hide.
* **The log** — every denial is logged at WARNING with the user id and role.
  Under a 404-on-denial policy that line is the only server-side way to
  triage "the user says they get a 404".

The first PMO managers come from configuration, not by hand:
``BOOTSTRAP_ADMIN_EMAILS`` lists them, and ``elevate_if_bootstrap_admin``
raises a listed user to ``pmo_manager`` at startup
(``app.services.bootstrap_admins``) and at row creation (SSO JIT
provisioning, local ``register``). Elevate-only — nothing here ever lowers a
role — so a list edit can never lock a manager out.
"""

import logging
import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Protocol

from app.config import settings
from app.models.enums import GLOBAL_ROLES, Role
from app.models.user import User
from app.utils.exceptions import AuthorizationError, NotFoundError

logger = logging.getLogger(__name__)

_KNOWN_ROLES = frozenset(role.value for role in Role)


class Principal(Protocol):
    """Whoever a request acts for. Read-only, so ``User`` satisfies it."""

    @property
    def id(self) -> uuid.UUID: ...

    @property
    def role(self) -> str | None: ...


@dataclass(frozen=True)
class PlacementPeople:
    """The people a placement names, which is what scopes it."""

    ps_user_id: uuid.UUID | None
    sme_user_id: uuid.UUID | None
    tech_lead_user_id: uuid.UUID | None

    def names(self, user_id: uuid.UUID) -> bool:
        return user_id in {self.ps_user_id, self.sme_user_id, self.tech_lead_user_id}


def bootstrap_admin_emails() -> frozenset[str]:
    """The configured bootstrap emails, normalised for matching.

    Lower-cased and stripped, blank entries dropped, so ``" A@x.com ,,"`` is
    ``{"a@x.com"}``. Read from settings on every call: the list is tiny, and
    reading it late lets a test change the setting without reloading modules.
    """
    return frozenset(
        part.strip().lower()
        for part in settings.bootstrap_admin_emails.split(",")
        if part.strip()
    )


def is_bootstrap_admin(email: str) -> bool:
    """True when ``email`` is on the configured list (case-insensitive)."""
    return email.strip().lower() in bootstrap_admin_emails()


def elevate_if_bootstrap_admin(user: User) -> bool:
    """Give ``user`` the ``pmo_manager`` role when they are on the list.

    Elevate-only and idempotent: an unlisted user is never touched, and a
    listed user who already holds a global role (``pmo_manager`` or
    ``admin``) is left alone. Returns True only when the row changed; the
    caller flushes or commits. Logged at INFO because a grant of every
    placement is worth a line in CloudWatch.
    """
    if not is_bootstrap_admin(user.email):
        return False
    if has_global_scope(user):
        return False
    logger.info(
        "Bootstrap admin elevated: user_id=%s email=%s role=%s->%s",
        user.id,
        user.email,
        user.role,
        Role.PMO_MANAGER.value,
    )
    user.role = Role.PMO_MANAGER.value
    return True


def has_global_scope(user: Principal) -> bool:
    """True when ``user`` reads every placement. ``None`` and unknown are False."""
    return user.role in GLOBAL_ROLES


def can_read_placement(user: Principal, people: PlacementPeople) -> bool:
    """True when ``user`` may read the placement naming ``people``."""
    if has_global_scope(user):
        return True
    if user.role not in _KNOWN_ROLES:
        return False
    return people.names(user.id)


def assert_can_read_placement(
    user: Principal,
    people: PlacementPeople,
    placement_id: uuid.UUID,
    resource: str = "Placement",
) -> None:
    """Raise ``NotFoundError`` unless ``user`` may read the placement.

    The error is built exactly as a genuinely missing row's would be, so the
    response cannot distinguish "does not exist" from "exists, not yours".
    ``resource`` lets a sub-resource (a session, a flag) name itself.
    """
    if can_read_placement(user, people):
        return
    _log_denial(user, "read", resource, placement_id)
    raise NotFoundError(resource, str(placement_id))


def assert_has_role(user: Principal, roles: Iterable[Role], resource: str) -> None:
    """Raise ``AuthorizationError`` (403) unless ``user`` holds one of ``roles``.

    For operations that address no placement — admin pages, the queue
    status. ``resource`` is the request path, so the log names the endpoint.
    """
    allowed = {role.value for role in roles}
    if user.role in allowed:
        return
    _log_denial(user, "role", resource, None)
    raise AuthorizationError("Not authorised for this operation")


def _log_denial(
    user: Principal,
    action: str,
    resource: str,
    resource_id: uuid.UUID | None,
) -> None:
    logger.warning(
        "Access denied: action=%s resource=%s resource_id=%s user_id=%s role=%s",
        action,
        resource,
        resource_id,
        user.id,
        user.role,
    )

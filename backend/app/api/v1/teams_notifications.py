"""Where Microsoft Graph posts Teams chat changes and subscription lifecycle events.

Public (Graph has no user): each route carries ``require_graph_client_state``,
which keeps only the notifications carrying this app's client state. When a
subscription is made, Graph first posts a ``validationToken`` to each URL and
needs it back as text/plain within 10 seconds. A notification is answered 202
at once: it only queues work (``services/teams/notifications``).

Rate limit: requests without a user share the load balancer's address as
their key, so these routes have their own, higher limit rather than the
default one shared with sign-in.
"""

from fastapi import APIRouter, Request, Response, status
from fastapi.responses import PlainTextResponse

from app.dependencies import DbSession, GraphNotificationBatch
from app.rate_limiter import limiter
from app.services.teams.notifications import handle_changes, handle_lifecycle

router = APIRouter()

NOTIFICATION_LIMIT = "600/minute"


def _validation(token: str) -> PlainTextResponse:
    return PlainTextResponse(token, status_code=status.HTTP_200_OK)


@router.post("/teams/notifications", response_model=None)
@limiter.limit(NOTIFICATION_LIMIT)
async def teams_notifications(
    request: Request, batch: GraphNotificationBatch, db: DbSession
) -> Response:
    """Changes to watched chats' messages: each chat's sync is queued."""
    if batch.validation_token is not None:
        return _validation(batch.validation_token)
    await handle_changes(db, batch.items)
    return Response(status_code=status.HTTP_202_ACCEPTED)


@router.post("/teams/lifecycle", response_model=None)
@limiter.limit(NOTIFICATION_LIMIT)
async def teams_lifecycle(
    request: Request, batch: GraphNotificationBatch, db: DbSession
) -> Response:
    """Subscription lifecycle events: renew, make again, or sync what was missed."""
    if batch.validation_token is not None:
        return _validation(batch.validation_token)
    await handle_lifecycle(db, batch.items)
    return Response(status_code=status.HTTP_202_ACCEPTED)

"""Stop an oversized request body as it arrives, before it is spooled.

Starlette parses a multipart upload into a temporary file before the route
runs, so the upload service's running byte cap only fires once the whole
body is on the task's disk. This middleware counts the bytes of the guarded
routes' bodies as they are received and answers 413 as soon as they pass the
limit: at once when ``Content-Length`` already says so, otherwise mid-stream
(chunked uploads too). Other routes pass through untouched.
"""

from starlette.exceptions import HTTPException
from starlette.types import ASGIApp, Message, Receive, Scope, Send

TOO_LARGE = "Request body too large"


class BodyLimitMiddleware:
    def __init__(self, app: ASGIApp, *, limits: dict[tuple[str, str], int]) -> None:
        """``limits`` maps (method, path) to the most bytes a body may have."""
        self.app = app
        self.limits = limits

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        limit = self.limits.get((scope["method"], scope["path"]))
        if limit is None:
            await self.app(scope, receive, send)
            return

        declared = dict(scope["headers"]).get(b"content-length")
        if declared is not None and declared.isdigit() and int(declared) > limit:
            await _too_large(send)
            return

        received = 0

        async def counting_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    # Raised inside body parsing; FastAPI passes an
                    # HTTPException through, so the client gets a 413.
                    raise HTTPException(status_code=413, detail=TOO_LARGE)
            return message

        await self.app(scope, counting_receive, send)


async def _too_large(send: Send) -> None:
    body = b'{"detail":"' + TOO_LARGE.encode() + b'"}'
    await send(
        {
            "type": "http.response.start",
            "status": 413,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode()),
                (b"connection", b"close"),
            ],
        }
    )
    await send({"type": "http.response.body", "body": body})

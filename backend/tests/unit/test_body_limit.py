"""The upload body limit: an oversized body is refused as it arrives."""

from collections.abc import AsyncIterator

import pytest
from fastapi import FastAPI, File, UploadFile
from httpx import ASGITransport, AsyncClient

from app.middleware.body_limit import BodyLimitMiddleware

LIMIT = 4096


def _app() -> FastAPI:
    app = FastAPI()
    seen: list[int] = []

    @app.post("/upload")
    async def upload(file: UploadFile = File(...)) -> dict[str, int]:
        size = len(await file.read())
        seen.append(size)
        return {"size": size}

    @app.post("/other")
    async def other(file: UploadFile = File(...)) -> dict[str, int]:
        return {"size": len(await file.read())}

    app.state.seen = seen
    app.add_middleware(BodyLimitMiddleware, limits={("POST", "/upload"): LIMIT})
    return app


def _multipart(payload: bytes) -> tuple[bytes, str]:
    boundary = "b0undary"
    body = (
        (
            f'--{boundary}\r\nContent-Disposition: form-data; name="file"; '
            f'filename="a.webm"\r\nContent-Type: video/webm\r\n\r\n'
        ).encode()
        + payload
        + f"\r\n--{boundary}--\r\n".encode()
    )
    return body, f"multipart/form-data; boundary={boundary}"


@pytest.fixture
def app() -> FastAPI:
    return _app()


async def _post(
    app: FastAPI, path: str, payload: bytes, *, chunked: bool = False
) -> int:
    body, content_type = _multipart(payload)
    content: bytes | AsyncIterator[bytes] = body
    if chunked:

        async def chunks() -> AsyncIterator[bytes]:
            for i in range(0, len(body), 512):
                yield body[i : i + 512]

        content = chunks()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        response = await c.post(
            path, content=content, headers={"content-type": content_type}
        )
    return response.status_code


class TestBodyLimit:
    async def test_body_within_the_limit_reaches_the_route(self, app: FastAPI) -> None:
        assert await _post(app, "/upload", b"x" * 1000) == 200
        assert app.state.seen == [1000]

    async def test_declared_length_over_the_limit_is_refused_at_once(
        self, app: FastAPI
    ) -> None:
        assert await _post(app, "/upload", b"x" * (LIMIT * 2)) == 413
        assert app.state.seen == []

    async def test_chunked_body_is_stopped_once_it_passes_the_limit(
        self, app: FastAPI
    ) -> None:
        assert await _post(app, "/upload", b"x" * (LIMIT * 2), chunked=True) == 413
        assert app.state.seen == []

    async def test_other_routes_are_not_limited(self, app: FastAPI) -> None:
        assert await _post(app, "/other", b"x" * (LIMIT * 2)) == 200

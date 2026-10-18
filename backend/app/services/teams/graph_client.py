"""Microsoft Graph for Teams chat: app-only sign-in and paced, retried requests.

The Graph app signs in with its certificate (the base64 of its .pfx and the
password, from settings); msal makes the token, which is kept until shortly
before it expires. Every request goes through one ``httpx.AsyncClient`` with
a finite timeout:

- **Pacing**: Graph allows one request per second per chat (and per user for
  a user's chat list), and enforces about 83% of that as a sustained rate, so
  requests that name one chat or user are spaced ``PER_RESOURCE_INTERVAL``
  apart.
- **Retries**: a 429, 503 or 504 is retried up to ``graph_max_retries``
  times, after the ``Retry-After`` seconds when Graph gives them, else after
  an exponential backoff.
- **Paging**: ``get_all`` follows ``@odata.nextLink`` to the last page.

Any failure (a refusal, an error after the retries, no answer, a token
refused) is a ``GraphError``. Nothing here logs a message body.
"""

import asyncio
import base64
import binascii
import logging
import re
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any, Protocol

import httpx
import msal
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    pkcs12,
)

from app.config import settings
from app.utils.exceptions import GraphError

logger = logging.getLogger(__name__)

GRAPH_BASE_URL = "https://graph.microsoft.com/v1.0"
GRAPH_SCOPE = "https://graph.microsoft.com/.default"
# One request per chat (or user) every 1.25 s: under Microsoft's 1 per second
# and its sustained 83% of it.
PER_RESOURCE_INTERVAL = 1.25
# A token is renewed this long before it expires.
TOKEN_RENEW_MARGIN_SECONDS = 300
MAX_BACKOFF_SECONDS = 60.0
RETRY_STATUSES = frozenset({429, 503, 504})
# The chat or user a request names, for pacing.
_PACED_RESOURCE = re.compile(r"/(chats|users)/([^/?]+)")

Json = dict[str, Any]


def certificate_credential(pfx_base64: str, password: str) -> dict[str, str]:
    """msal's client credential from a .pfx: its private key and certificate as PEM.

    Raises GraphError when the .pfx cannot be read with the password.
    """
    try:
        pfx = base64.b64decode(pfx_base64, validate=True)
        key, cert, _ = pkcs12.load_key_and_certificates(
            pfx, password.encode() if password else None
        )
    except (binascii.Error, ValueError) as exc:
        raise GraphError("The Graph certificate could not be read") from exc
    if key is None or cert is None:
        raise GraphError("The Graph certificate holds no private key or certificate")
    return {
        "private_key": key.private_bytes(
            Encoding.PEM, PrivateFormat.PKCS8, NoEncryption()
        ).decode(),
        "public_certificate": cert.public_bytes(Encoding.PEM).decode(),
    }


class TokenSource(Protocol):
    async def token(self) -> str: ...


class MsalTokenSource:
    """App-only Graph tokens from the certificate, kept until shortly before expiry."""

    def __init__(
        self,
        tenant_id: str,
        client_id: str,
        credential: dict[str, str],
        *,
        app_factory: Callable[..., Any] = msal.ConfidentialClientApplication,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._tenant_id = tenant_id
        self._client_id = client_id
        self._credential = credential
        self._app_factory = app_factory
        self._clock = clock
        self._app: Any = None
        self._token: str | None = None
        self._expires_at = 0.0
        self._lock = asyncio.Lock()

    def _acquire(self) -> Json:
        if self._app is None:
            self._app = self._app_factory(
                self._client_id,
                authority=f"https://login.microsoftonline.com/{self._tenant_id}",
                client_credential=self._credential,
            )
        result: Json = self._app.acquire_token_for_client(scopes=[GRAPH_SCOPE])
        return result

    async def token(self) -> str:
        async with self._lock:
            if (
                self._token is not None
                and self._clock() < self._expires_at - TOKEN_RENEW_MARGIN_SECONDS
            ):
                return self._token
            try:
                # msal is synchronous: the token request runs in a worker thread.
                result = await asyncio.to_thread(self._acquire)
            except Exception as exc:  # msal raises requests' and its own errors
                raise GraphError(f"Graph token request failed: {exc}") from exc
            if "access_token" not in result:
                raise GraphError(
                    "Graph token refused: "
                    f"{result.get('error')}: {result.get('error_description')}"
                )
            self._token = str(result["access_token"])
            self._expires_at = self._clock() + float(result.get("expires_in", 3599))
            return self._token


def _retry_after(response: httpx.Response) -> float | None:
    """Graph's ``Retry-After`` in seconds, when it gives a number."""
    value = response.headers.get("Retry-After")
    if value is None:
        return None
    try:
        return max(float(value), 0.0)
    except ValueError:
        return None


def _error(method: str, path: str, response: httpx.Response) -> GraphError:
    code: str | None = None
    message = ""
    try:
        error = response.json().get("error", {})
        code = error.get("code")
        message = error.get("message") or ""
    except (ValueError, AttributeError):
        pass
    return GraphError(
        f"Graph {method} {path} answered {response.status_code}: {code}: {message}",
        graph_status=response.status_code,
        graph_code=code,
    )


class GraphClient:
    """Requests to Microsoft Graph v1.0, paced per chat and retried when throttled."""

    def __init__(
        self,
        tokens: TokenSource,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        timeout_seconds: float | None = None,
        max_retries: int | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._tokens = tokens
        self._http = httpx.AsyncClient(
            base_url=GRAPH_BASE_URL,
            timeout=(
                timeout_seconds
                if timeout_seconds is not None
                else settings.graph_timeout_seconds
            ),
            transport=transport,
        )
        self._max_retries = (
            max_retries if max_retries is not None else settings.graph_max_retries
        )
        self._sleep = sleep
        self._clock = clock
        self._last_request: dict[str, float] = {}
        self._pace_locks: dict[str, asyncio.Lock] = {}

    async def aclose(self) -> None:
        await self._http.aclose()

    async def get(self, path: str, params: dict[str, str] | None = None) -> Json:
        return _json("GET", path, await self._request("GET", path, params=params))

    async def get_all(
        self, path: str, params: dict[str, str] | None = None
    ) -> AsyncIterator[Json]:
        """Every item of a collection, page after page."""
        url: str | None = path
        query = params
        while url is not None:
            page = _json("GET", path, await self._request("GET", url, params=query))
            for item in page.get("value", []):
                yield item
            url = page.get("@odata.nextLink")
            query = None  # the next link carries the query

    async def post(self, path: str, body: Json) -> Json:
        return _json("POST", path, await self._request("POST", path, body=body))

    async def patch(self, path: str, body: Json) -> Json:
        response = await self._request("PATCH", path, body=body)
        return _json("PATCH", path, response) if response.content else {}

    async def delete(self, path: str) -> None:
        await self._request("DELETE", path)

    async def _pace(self, resource: str) -> None:
        lock = self._pace_locks.setdefault(resource, asyncio.Lock())
        async with lock:
            last = self._last_request.get(resource)
            if last is not None:
                wait = last + PER_RESOURCE_INTERVAL - self._clock()
                if wait > 0:
                    await self._sleep(wait)
            self._last_request[resource] = self._clock()

    async def _request(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, str] | None = None,
        body: Json | None = None,
    ) -> httpx.Response:
        path = httpx.URL(url).path
        paced = _PACED_RESOURCE.search(path)
        for attempt in range(self._max_retries + 1):
            if paced is not None:
                await self._pace(paced.group(0))
            token = await self._tokens.token()
            try:
                response = await self._http.request(
                    method,
                    url,
                    params=params,
                    json=body,
                    headers={"Authorization": f"Bearer {token}"},
                )
            except httpx.HTTPError as exc:
                raise GraphError(f"Graph {method} {path} failed: {exc!r}") from exc
            if response.status_code in RETRY_STATUSES and attempt < self._max_retries:
                delay = _retry_after(response)
                if delay is None:
                    delay = min(2.0**attempt, MAX_BACKOFF_SECONDS)
                logger.warning(
                    "Graph %s %s answered %d; retry %d of %d in %.1f s",
                    method,
                    path,
                    response.status_code,
                    attempt + 1,
                    self._max_retries,
                    delay,
                )
                await self._sleep(delay)
                continue
            if response.is_success:
                return response
            raise _error(method, path, response)
        raise AssertionError("unreachable: the last attempt returns or raises")


def _json(method: str, path: str, response: httpx.Response) -> Json:
    try:
        data = response.json()
    except ValueError as exc:
        raise GraphError(f"Graph {method} {path} answered without JSON") from exc
    if not isinstance(data, dict):
        raise GraphError(f"Graph {method} {path} answered with a non-object")
    return data


def graph_client_from_settings() -> GraphClient:
    """A Graph client signed in as the Graph app named in settings.

    Raises GraphError when the Graph settings are missing or the certificate
    cannot be read.
    """
    missing = [
        name
        for name, value in (
            ("GRAPH_TENANT_ID", settings.graph_tenant_id),
            ("GRAPH_CLIENT_ID", settings.graph_client_id),
            ("GRAPH_CERTIFICATE_PFX_BASE64", settings.graph_certificate_pfx_base64),
        )
        if not value
    ]
    if missing:
        raise GraphError(f"Graph is not configured: {', '.join(missing)} not set")
    credential = certificate_credential(
        settings.graph_certificate_pfx_base64, settings.graph_certificate_password
    )
    return GraphClient(
        MsalTokenSource(settings.graph_tenant_id, settings.graph_client_id, credential)
    )


_shared: GraphClient | None = None


def get_graph_client() -> GraphClient:
    """The process's one Graph client (one token, one connection pool), made on
    first use from settings. Raises GraphError when Graph is not configured."""
    global _shared
    if _shared is None:
        _shared = graph_client_from_settings()
    return _shared


async def close_graph_client() -> None:
    """Close the shared client at shutdown; the next use makes a new one."""
    global _shared
    if _shared is not None:
        await _shared.aclose()
        _shared = None

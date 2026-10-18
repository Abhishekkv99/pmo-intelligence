"""The Graph client: the certificate read, the token kept until near expiry, paging,
pacing per chat, Retry-After and backoff with a limit, and every failure a GraphError.

Every request goes to an ``httpx.MockTransport``; nothing calls Microsoft.
"""

import base64
import datetime as dt
import json
from typing import Any

import httpx
import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import (
    BestAvailableEncryption,
    pkcs12,
)
from cryptography.x509.oid import NameOID

from app.config import settings
from app.services.teams import graph_client
from app.services.teams.graph_client import (
    GRAPH_SCOPE,
    PER_RESOURCE_INTERVAL,
    TOKEN_RENEW_MARGIN_SECONDS,
    GraphClient,
    MsalTokenSource,
    certificate_credential,
    graph_client_from_settings,
)
from app.utils.exceptions import GraphError

CHAT = "19:abc@thread.v2"


def _pfx_base64(password: str) -> str:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "graph-test")])
    now = dt.datetime.now(dt.UTC)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now)
        .not_valid_after(now + dt.timedelta(days=1))
        .sign(key, hashes.SHA256())
    )
    pfx = pkcs12.serialize_key_and_certificates(
        b"graph-test", key, cert, None, BestAvailableEncryption(password.encode())
    )
    return base64.b64encode(pfx).decode()


class _Clock:
    """A clock that only the fake sleep moves."""

    def __init__(self) -> None:
        self.now = 1000.0
        self.slept: list[float] = []

    def __call__(self) -> float:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds


class _Tokens:
    def __init__(self) -> None:
        self.calls = 0

    async def token(self) -> str:
        self.calls += 1
        return "tok"


def _client(
    handler: Any, clock: _Clock | None = None, max_retries: int = 3
) -> GraphClient:
    clock = clock or _Clock()
    return GraphClient(
        _Tokens(),
        transport=httpx.MockTransport(handler),
        max_retries=max_retries,
        sleep=clock.sleep,
        clock=clock,
    )


class TestCertificateCredential:
    def test_reads_the_key_and_certificate_as_pem(self) -> None:
        credential = certificate_credential(_pfx_base64("s3cret"), "s3cret")

        assert credential["private_key"].startswith("-----BEGIN PRIVATE KEY-----")
        assert credential["public_certificate"].startswith(
            "-----BEGIN CERTIFICATE-----"
        )

    def test_a_wrong_password_is_a_graph_error(self) -> None:
        with pytest.raises(GraphError, match="could not be read"):
            certificate_credential(_pfx_base64("s3cret"), "wrong")

    def test_text_that_is_not_base64_is_a_graph_error(self) -> None:
        with pytest.raises(GraphError, match="could not be read"):
            certificate_credential("not base64!", "s3cret")


class _FakeMsalApp:
    def __init__(self, results: list[dict[str, Any] | Exception]) -> None:
        self.results = results
        self.scopes: list[list[str]] = []

    def acquire_token_for_client(self, scopes: list[str]) -> dict[str, Any]:
        self.scopes.append(scopes)
        result = self.results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


class TestMsalTokenSource:
    def _source(
        self, app: _FakeMsalApp, clock: _Clock
    ) -> tuple[MsalTokenSource, list[dict[str, Any]]]:
        built: list[dict[str, Any]] = []

        def factory(client_id: str, **kwargs: Any) -> _FakeMsalApp:
            built.append({"client_id": client_id, **kwargs})
            return app

        source = MsalTokenSource(
            "tenant-1",
            "client-1",
            {"private_key": "k", "public_certificate": "c"},
            app_factory=factory,
            clock=clock,
        )
        return source, built

    async def test_builds_the_app_for_the_tenant_once_and_reuses_the_token(
        self,
    ) -> None:
        clock = _Clock()
        app = _FakeMsalApp([{"access_token": "a1", "expires_in": 3599}])
        source, built = self._source(app, clock)

        assert await source.token() == "a1"
        clock.now += 3599 - TOKEN_RENEW_MARGIN_SECONDS - 1
        assert await source.token() == "a1"

        assert app.scopes == [[GRAPH_SCOPE]]
        assert built == [
            {
                "client_id": "client-1",
                "authority": "https://login.microsoftonline.com/tenant-1",
                "client_credential": {"private_key": "k", "public_certificate": "c"},
            }
        ]

    async def test_renews_the_token_shortly_before_it_expires(self) -> None:
        clock = _Clock()
        app = _FakeMsalApp(
            [
                {"access_token": "a1", "expires_in": 3599},
                {"access_token": "a2", "expires_in": 3599},
            ]
        )
        source, built = self._source(app, clock)

        assert await source.token() == "a1"
        clock.now += 3599 - TOKEN_RENEW_MARGIN_SECONDS
        assert await source.token() == "a2"
        assert len(built) == 1

    async def test_a_refused_token_is_a_graph_error(self) -> None:
        app = _FakeMsalApp(
            [{"error": "invalid_client", "error_description": "bad certificate"}]
        )
        source, _ = self._source(app, _Clock())

        with pytest.raises(GraphError, match="invalid_client: bad certificate"):
            await source.token()

    async def test_a_failed_token_request_is_a_graph_error(self) -> None:
        app = _FakeMsalApp([ConnectionError("no route")])
        source, _ = self._source(app, _Clock())

        with pytest.raises(GraphError, match="no route"):
            await source.token()


class TestRequests:
    async def test_sends_the_bearer_token_to_graph_v1(self) -> None:
        seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(request)
            return httpx.Response(200, json={"id": "me"})

        client = _client(handler)
        assert await client.get("/subscriptions/s-1") == {"id": "me"}

        assert str(seen[0].url) == "https://graph.microsoft.com/v1.0/subscriptions/s-1"
        assert seen[0].headers["Authorization"] == "Bearer tok"

    async def test_get_all_follows_the_next_link_to_the_last_page(self) -> None:
        urls: list[str] = []
        next_link = (
            f"https://graph.microsoft.com/v1.0/chats/{CHAT}/messages?$skiptoken=p2"
        )

        def handler(request: httpx.Request) -> httpx.Response:
            urls.append(str(request.url))
            if "skiptoken" in str(request.url):
                return httpx.Response(200, json={"value": [{"id": "3"}]})
            return httpx.Response(
                200,
                json={
                    "value": [{"id": "1"}, {"id": "2"}],
                    "@odata.nextLink": next_link,
                },
            )

        client = _client(handler)
        items = [
            item
            async for item in client.get_all(
                f"/chats/{CHAT}/messages", params={"$top": "50"}
            )
        ]

        assert [item["id"] for item in items] == ["1", "2", "3"]
        assert "%24top=50" in urls[0]
        # The next link is sent as Graph gave it.
        assert urls[1] == next_link

    async def test_post_sends_the_body_and_reads_the_answer(self) -> None:
        bodies: list[Any] = []

        def handler(request: httpx.Request) -> httpx.Response:
            bodies.append(json.loads(request.content))
            return httpx.Response(201, json={"id": "s-1"})

        client = _client(handler)
        answer = await client.post("/subscriptions", {"changeType": "created"})

        assert answer == {"id": "s-1"}
        assert bodies == [{"changeType": "created"}]

    async def test_patch_without_content_and_delete_answer_nothing(self) -> None:
        methods: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            methods.append(request.method)
            return httpx.Response(204)

        client = _client(handler)

        assert (
            await client.patch("/subscriptions/s-1", {"expirationDateTime": "x"}) == {}
        )
        await client.delete("/subscriptions/s-1")

        assert methods == ["PATCH", "DELETE"]

    async def test_an_answer_without_json_is_a_graph_error(self) -> None:
        client = _client(lambda request: httpx.Response(200, text="<html>"))

        with pytest.raises(GraphError, match="without JSON"):
            await client.get("/subscriptions")


class TestRetries:
    async def test_waits_the_retry_after_seconds_then_succeeds(self) -> None:
        answers = [
            httpx.Response(429, headers={"Retry-After": "7"}),
            httpx.Response(200, json={"ok": True}),
        ]
        clock = _Clock()
        client = _client(lambda request: answers.pop(0), clock)

        assert await client.get("/subscriptions") == {"ok": True}
        assert clock.slept == [7.0]

    async def test_backs_off_exponentially_without_retry_after(self) -> None:
        answers = [
            httpx.Response(503),
            httpx.Response(504),
            httpx.Response(200, json={"ok": True}),
        ]
        clock = _Clock()
        client = _client(lambda request: answers.pop(0), clock)

        assert await client.get("/subscriptions") == {"ok": True}
        assert clock.slept == [1.0, 2.0]

    async def test_gives_up_after_the_retry_limit(self) -> None:
        calls = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            return httpx.Response(
                429, json={"error": {"code": "TooManyRequests", "message": "slow"}}
            )

        clock = _Clock()
        client = _client(handler, clock, max_retries=2)

        with pytest.raises(GraphError) as caught:
            await client.get("/subscriptions")

        assert calls == 3
        assert clock.slept == [1.0, 2.0]
        assert caught.value.graph_status == 429
        assert caught.value.graph_code == "TooManyRequests"

    async def test_a_refusal_is_not_retried_and_names_graphs_code(self) -> None:
        calls = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            return httpx.Response(
                403, json={"error": {"code": "Forbidden", "message": "No access"}}
            )

        client = _client(handler)

        with pytest.raises(GraphError, match="403: Forbidden: No access") as caught:
            await client.get(f"/chats/{CHAT}/messages")

        assert calls == 1
        assert caught.value.graph_status == 403
        assert caught.value.status_code == 502

    async def test_no_answer_is_a_graph_error_without_a_status(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("refused", request=request)

        client = _client(handler)

        with pytest.raises(GraphError, match="failed") as caught:
            await client.get("/subscriptions")

        assert caught.value.graph_status is None


class TestPacing:
    async def test_spaces_requests_to_one_chat(self) -> None:
        clock = _Clock()
        client = _client(lambda request: httpx.Response(200, json={}), clock)

        await client.get(f"/chats/{CHAT}/messages")
        await client.get(f"/chats/{CHAT}/members")

        assert clock.slept == [PER_RESOURCE_INTERVAL]

    async def test_does_not_wait_once_the_interval_has_passed(self) -> None:
        clock = _Clock()
        client = _client(lambda request: httpx.Response(200, json={}), clock)

        await client.get(f"/chats/{CHAT}/messages")
        clock.now += PER_RESOURCE_INTERVAL
        await client.get(f"/chats/{CHAT}/messages")

        assert clock.slept == []

    async def test_different_chats_and_unpaced_paths_do_not_wait(self) -> None:
        clock = _Clock()
        client = _client(lambda request: httpx.Response(200, json={}), clock)

        await client.get(f"/chats/{CHAT}/messages")
        await client.get("/chats/19:other@thread.v2/messages")
        await client.get("/subscriptions")
        await client.get("/subscriptions")

        assert clock.slept == []

    async def test_one_users_chat_list_is_paced_too(self) -> None:
        clock = _Clock()
        client = _client(lambda request: httpx.Response(200, json={}), clock)

        await client.get("/users/ana@example.com/chats")
        await client.get("/users/ana@example.com/chats")

        assert clock.slept == [PER_RESOURCE_INTERVAL]


class TestFromSettings:
    def test_missing_settings_are_named(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(settings, "graph_tenant_id", "")
        monkeypatch.setattr(settings, "graph_client_id", "client-1")
        monkeypatch.setattr(settings, "graph_certificate_pfx_base64", "")

        with pytest.raises(
            GraphError, match="GRAPH_TENANT_ID, GRAPH_CERTIFICATE_PFX_BASE64 not set"
        ):
            graph_client_from_settings()

    async def test_builds_a_client_from_the_certificate(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "graph_tenant_id", "tenant-1")
        monkeypatch.setattr(settings, "graph_client_id", "client-1")
        monkeypatch.setattr(
            settings, "graph_certificate_pfx_base64", _pfx_base64("s3cret")
        )
        monkeypatch.setattr(settings, "graph_certificate_password", "s3cret")

        client = graph_client_from_settings()

        assert isinstance(client, graph_client.GraphClient)
        await client.aclose()

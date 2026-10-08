"""The SSRF guard: public addresses only, the checked address pinned, every
redirect hop checked again."""

import ipaddress

import httpx
import pytest

from app.services.url_guard import (
    check_url,
    is_public_address,
    pinned_request,
    resolve_public,
    send_guarded,
)
from app.utils.exceptions import ValidationError

PUBLIC = "93.184.215.14"


def _resolver(table: dict[str, list[str]]):  # type: ignore[no-untyped-def]
    async def resolve(host: str, port: int) -> list[str]:
        if host not in table:
            raise OSError("no such host")
        return table[host]

    return resolve


class TestIsPublicAddress:
    @pytest.mark.parametrize(
        "address",
        [
            "10.0.0.5",
            "172.16.4.1",
            "192.168.1.10",
            "127.0.0.1",
            "169.254.169.254",
            "100.64.0.1",
            "0.0.0.0",
            "224.0.0.1",
            "::1",
            "fe80::1",
            "fd00:ec2::254",
            "::ffff:127.0.0.1",
            "::ffff:169.254.169.254",
        ],
    )
    def test_internal_address_is_refused(self, address: str) -> None:
        assert not is_public_address(ipaddress.ip_address(address))

    @pytest.mark.parametrize(
        "address", [PUBLIC, "2606:2800:21f:cb07:6820:80da:af6b:8b2c"]
    )
    def test_public_address_is_allowed(self, address: str) -> None:
        assert is_public_address(ipaddress.ip_address(address))


class TestCheckUrl:
    @pytest.mark.parametrize(
        "url",
        ["http://example.com/a.webm", "ftp://example.com/a.webm", "file:///etc/passwd"],
    )
    def test_anything_but_https_is_refused(self, url: str) -> None:
        with pytest.raises(ValidationError, match="https://"):
            check_url(url)

    def test_https_url_is_parsed(self) -> None:
        assert check_url("https://example.com/a.webm").host == "example.com"


class TestResolvePublic:
    async def test_host_resolving_only_to_public_addresses_gives_the_first(
        self,
    ) -> None:
        address = await resolve_public(
            check_url("https://example.com/a.webm"),
            _resolver({"example.com": [PUBLIC, "93.184.215.15"]}),
        )
        assert str(address) == PUBLIC

    async def test_host_with_any_internal_address_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="private or internal"):
            await resolve_public(
                check_url("https://mixed.example/a.webm"),
                _resolver({"mixed.example": [PUBLIC, "10.0.0.5"]}),
            )

    @pytest.mark.parametrize(
        "url", ["https://169.254.169.254/latest/meta-data/", "https://[::1]/a.webm"]
    )
    async def test_internal_ip_literal_is_refused_without_a_lookup(
        self, url: str
    ) -> None:
        with pytest.raises(ValidationError, match="private or internal"):
            await resolve_public(check_url(url), _resolver({}))

    async def test_unresolvable_host_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="Could not resolve"):
            await resolve_public(check_url("https://nowhere.example/"), _resolver({}))


class TestPinnedRequest:
    async def test_request_goes_to_the_checked_address_with_the_host_name_kept(
        self,
    ) -> None:
        async with httpx.AsyncClient() as client:
            request = pinned_request(
                client,
                "GET",
                check_url("https://media.example.com:8443/r.webm?sig=1"),
                ipaddress.ip_address(PUBLIC),
            )
        assert request.url.host == PUBLIC
        assert request.url.port == 8443
        assert request.url.path == "/r.webm"
        assert request.url.query == b"sig=1"
        assert request.headers["host"] == "media.example.com:8443"
        assert request.extensions["sni_hostname"] == "media.example.com"

    async def test_ipv6_address_is_pinned(self) -> None:
        address = ipaddress.ip_address("2606:2800:21f:cb07:6820:80da:af6b:8b2c")
        async with httpx.AsyncClient() as client:
            request = pinned_request(
                client, "GET", check_url("https://media.example.com/r.webm"), address
            )
        assert request.url.host == str(address)
        assert request.headers["host"] == "media.example.com"


class TestSendGuarded:
    async def test_redirect_to_an_internal_host_is_refused(self) -> None:
        sent: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            sent.append(request.headers["host"])
            return httpx.Response(
                302, headers={"location": "https://internal.example/latest"}
            )

        resolver = _resolver(
            {"media.example.com": [PUBLIC], "internal.example": ["169.254.169.254"]}
        )
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            with pytest.raises(ValidationError, match="private or internal"):
                await send_guarded(
                    client,
                    "GET",
                    "https://media.example.com/r.webm",
                    max_redirects=5,
                    resolver=resolver,
                )
        assert sent == ["media.example.com"]

    async def test_redirect_to_http_is_refused(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(302, headers={"location": "http://cdn.example/r"})

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            with pytest.raises(ValidationError, match="https://"):
                await send_guarded(
                    client,
                    "GET",
                    "https://media.example.com/r.webm",
                    max_redirects=5,
                    resolver=_resolver({"media.example.com": [PUBLIC]}),
                )

    async def test_public_redirect_is_followed_and_pinned_again(self) -> None:
        seen: list[tuple[str, str]] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append((str(request.url.host), request.headers["host"]))
            if request.headers["host"] == "media.example.com":
                return httpx.Response(
                    302, headers={"location": "https://cdn.example/r"}
                )
            return httpx.Response(200, content=b"ok")

        resolver = _resolver(
            {"media.example.com": [PUBLIC], "cdn.example": ["93.184.215.20"]}
        )
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            response, final_url = await send_guarded(
                client,
                "GET",
                "https://media.example.com/r.webm",
                max_redirects=5,
                resolver=resolver,
            )
            await response.aclose()
        assert response.status_code == 200
        assert str(final_url) == "https://cdn.example/r"
        assert seen == [
            (PUBLIC, "media.example.com"),
            ("93.184.215.20", "cdn.example"),
        ]

    async def test_too_many_redirects_are_refused(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(302, headers={"location": "/again"})

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            with pytest.raises(ValidationError, match="more than 2 times"):
                await send_guarded(
                    client,
                    "GET",
                    "https://media.example.com/r.webm",
                    max_redirects=2,
                    resolver=_resolver({"media.example.com": [PUBLIC]}),
                )

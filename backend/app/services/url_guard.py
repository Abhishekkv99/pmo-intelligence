"""Keep a recording URL from reaching anything but the public internet (SSRF).

A URL is only fetched over HTTPS, and only after every address its host
resolves to has been checked as public: no private, loopback, link-local
(which includes the 169.254.169.254 metadata service), carrier-grade NAT,
multicast or reserved address. The request then goes to the address that was
checked, not to a second lookup, so a host that answers with a public address
first and an internal one next (DNS rebinding) cannot slip through. TLS is
still verified against the host name, sent as SNI. Redirects are followed by
hand, and every hop is checked again.
"""

import asyncio
import ipaddress
import socket
from collections.abc import Awaitable, Callable

import httpx

from app.utils.exceptions import ValidationError

IPAddress = ipaddress.IPv4Address | ipaddress.IPv6Address
Resolver = Callable[[str, int], Awaitable[list[str]]]

REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})


def is_public_address(address: IPAddress) -> bool:
    """Whether a connection to ``address`` stays on the public internet."""
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped:
        address = address.ipv4_mapped
    return address.is_global and not address.is_multicast


async def system_resolver(host: str, port: int) -> list[str]:
    infos = await asyncio.get_running_loop().getaddrinfo(
        host, port, type=socket.SOCK_STREAM
    )
    return [str(info[4][0]) for info in infos]


def check_url(url: str | httpx.URL) -> httpx.URL:
    """Parse ``url``; HTTPS with a host only."""
    try:
        parsed = httpx.URL(url)
    except (httpx.InvalidURL, TypeError) as exc:
        raise ValidationError("Invalid URL") from exc
    if parsed.scheme != "https":
        raise ValidationError("The URL must start with https://")
    if not parsed.host:
        raise ValidationError("Invalid URL: missing host")
    return parsed


async def resolve_public(
    url: httpx.URL, resolver: Resolver = system_resolver
) -> IPAddress:
    """The address to connect to for ``url``; refuses unless every one is public."""
    host = url.raw_host.decode("ascii")
    try:
        literal: IPAddress | None = ipaddress.ip_address(host.strip("[]"))
    except ValueError:
        literal = None
    if literal is not None:
        addresses = [literal]
    else:
        try:
            found = await resolver(host, url.port or 443)
        except OSError as exc:
            raise ValidationError(f"Could not resolve the URL's host: {host}") from exc
        addresses = [ipaddress.ip_address(a.split("%", 1)[0]) for a in found]
    if not addresses:
        raise ValidationError(f"Could not resolve the URL's host: {host}")
    if not all(is_public_address(a) for a in addresses):
        raise ValidationError("The URL points to a private or internal address")
    return addresses[0]


def pinned_request(
    client: httpx.AsyncClient,
    method: str,
    url: httpx.URL,
    address: IPAddress,
    headers: dict[str, str] | None = None,
) -> httpx.Request:
    """A request for ``url`` sent to ``address``, with the host name as Host and SNI."""
    host = url.raw_host.decode("ascii")
    host_header = host if url.port is None else f"{host}:{url.port}"
    return client.build_request(
        method,
        url.copy_with(host=str(address)),
        headers={**(headers or {}), "Host": host_header},
        extensions={"sni_hostname": host},
    )


async def send_guarded(
    client: httpx.AsyncClient,
    method: str,
    url: str | httpx.URL,
    *,
    headers: dict[str, str] | None = None,
    max_redirects: int,
    resolver: Resolver = system_resolver,
) -> tuple[httpx.Response, httpx.URL]:
    """Send ``method`` to ``url`` with every hop checked; returns the streamed
    final response (the caller closes it) and the URL it came from."""
    target = check_url(url)
    for _ in range(max_redirects + 1):
        address = await resolve_public(target, resolver)
        request = pinned_request(client, method, target, address, headers)
        response = await client.send(request, stream=True, follow_redirects=False)
        location = response.headers.get("location")
        if response.status_code not in REDIRECT_STATUSES or not location:
            return response, target
        await response.aclose()
        target = check_url(target.join(location))
        if response.status_code == 303 and method != "HEAD":
            method = "GET"
    raise ValidationError(f"The URL redirected more than {max_redirects} times")

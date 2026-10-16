"""A local receiver for Microsoft Graph change notifications (Sprint 4 spike).

Answers Graph's validation request (echoes ?validationToken= as text/plain) and logs
each notification's subscription id, change type, resource path, lifecycle event and
how long after the message was created it arrived. Message bodies are never requested
or printed. Reach it from Graph through a temporary tunnel, e.g. Microsoft dev tunnels:

    devtunnel host -p 8765 --allow-anonymous

Usage:
    python scripts/teams/spike_receiver.py --port 8765 --client-state <secret>
"""

import argparse
import contextlib
import hmac
import json
import re
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

# A Teams message id is its creation time in epoch milliseconds:
# messages('1612289765949').
_MESSAGE_ID = re.compile(r"messages\('(\d{13})'\)")


def latency(resource: str) -> str:
    match = _MESSAGE_ID.search(resource)
    if not match:
        return "-"
    created = datetime.fromtimestamp(int(match.group(1)) / 1000, UTC)
    return f"{(datetime.now(UTC) - created).total_seconds():.1f} s after creation"


def make_handler(client_state: str) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            url = urlparse(self.path)
            query = parse_qs(url.query)
            if "validationToken" in query:
                token = query["validationToken"][0].encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/plain")
                self.send_header("Content-Length", str(len(token)))
                self.end_headers()
                self.wfile.write(token)
                print(
                    f"{datetime.now(UTC):%H:%M:%S} validation on {url.path}: answered",
                    flush=True,
                )
                return

            length = int(self.headers.get("Content-Length") or 0)
            try:
                body: dict[str, Any] = json.loads(self.rfile.read(length) or b"{}")
            except ValueError:
                body = {}
            self.send_response(202)
            self.end_headers()
            for n in body.get("value", []):
                ok = hmac.compare_digest(str(n.get("clientState", "")), client_state)
                resource = str(n.get("resource", ""))
                print(
                    f"{datetime.now(UTC):%H:%M:%S} "
                    f"{'OK ' if ok else 'BAD client state'} "
                    f"sub={n.get('subscriptionId')} change={n.get('changeType')} "
                    f"lifecycle={n.get('lifecycleEvent', '-')} {latency(resource)}\n"
                    f"         {resource}",
                    flush=True,
                )

        def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
            pass  # the notification lines above are the log

    return Handler


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--client-state", required=True)
    args = parser.parse_args()
    handler = make_handler(args.client_state)
    server = ThreadingHTTPServer(("127.0.0.1", args.port), handler)
    print(f"Listening on http://127.0.0.1:{args.port} (Ctrl+C to stop)")
    with contextlib.suppress(KeyboardInterrupt):
        server.serve_forever()


if __name__ == "__main__":
    main()

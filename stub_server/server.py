"""A stand-in for the real agent gateway.

Asks the configured feeders for the current list on every request, so what
the glasses show is never stale and there is only one thing to run.

Which feeders it uses comes from the environment. The default is invented
data, which needs no accounts and reveals nothing personal. See the README.

Bound to the loopback address on purpose. It serves whatever the feeders
return with no authentication at all, so it must never be reachable from a
network.
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ITEMS_PATH = "/items"
LOOPBACK_HOST = "127.0.0.1"
DEFAULT_PORT = 8765

DEFAULT_DATA_PATH = Path(__file__).parent / "agents.json"


class _ItemsHandler(BaseHTTPRequestHandler):
    """Serves the items file. The data path is set on the server object."""

    # Set by create_server.
    data_path: Path

    def do_GET(self) -> None:
        if self.path.split("?")[0] != ITEMS_PATH:
            self._respond(404, {"error": "not found"})
            return

        try:
            items = self.server.provider()
        except Exception as exc:  # a broken feeder must not take the gateway down
            self._respond(500, {"error": f"feeder failed: {exc}"})
            return

        self._respond(200, {"items": items})

    def _respond(self, status: int, payload: object) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt: str, *args: object) -> None:
        """Quieter than the default, which prints a line per request."""


class _ItemsServer(ThreadingHTTPServer):
    """A server that knows where to get its items."""

    daemon_threads = True

    def __init__(
        self, address: tuple[str, int], provider: Callable[[], list]
    ) -> None:
        self.provider = provider
        super().__init__(address, _ItemsHandler)


def create_server(
    provider: Callable[[], list], port: int = DEFAULT_PORT
) -> _ItemsServer:
    """Build a server bound to loopback.

    Args:
        provider: Called on every request; returns the current list.
        port: Pass 0 to be given a free one.
    """
    return _ItemsServer((LOOPBACK_HOST, port), provider)


def main() -> None:
    """Run the stub until interrupted."""
    from agent_hud.config import load_settings
    from feeders import collect

    settings = load_settings()
    port = int(os.environ.get("AGENT_HUD_PORT", DEFAULT_PORT))
    server = create_server(
        lambda: collect(settings, file_path=DEFAULT_DATA_PATH), port=port
    )
    host, bound_port = server.server_address[:2]
    print(f"Stub gateway on http://{host}:{bound_port}{ITEMS_PATH}")
    print(f"Feeders: {', '.join(settings.feeders)}")
    if "file" in settings.feeders:
        print(f"Editing {DEFAULT_DATA_PATH} changes what the glasses show.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()

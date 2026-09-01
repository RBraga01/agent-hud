"""A stand-in for the real agent gateway.

Reads a JSON file and serves it over HTTP. Edit the file and the glasses
pick up the change on their next request, which is how the display is
driven during development.

Standard library only, so it runs anywhere with nothing installed.

Bound to the loopback address on purpose. It serves whatever is in the
file with no authentication, so it must never be reachable from a
network.
"""

from __future__ import annotations

import json
import os
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
            raw = self.server.data_path.read_text(encoding="utf-8")
            payload = json.loads(raw)
        except FileNotFoundError:
            self._respond(500, {"error": "items file not found"})
            return
        except (json.JSONDecodeError, OSError) as exc:
            self._respond(500, {"error": f"items file unreadable: {exc}"})
            return

        self._respond(200, payload)

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
    """A server that knows which file to serve."""

    daemon_threads = True

    def __init__(self, address: tuple[str, int], data_path: Path) -> None:
        self.data_path = data_path
        super().__init__(address, _ItemsHandler)


def create_server(
    data_path: Path | str = DEFAULT_DATA_PATH, port: int = DEFAULT_PORT
) -> _ItemsServer:
    """Build a server bound to loopback. Pass port=0 to get a free port."""
    return _ItemsServer((LOOPBACK_HOST, port), Path(data_path))


def main() -> None:
    """Run the stub until interrupted."""
    port = int(os.environ.get("AGENT_HUD_PORT", DEFAULT_PORT))
    server = create_server(port=port)
    host, bound_port = server.server_address[:2]
    print(f"Stub gateway on http://{host}:{bound_port}{ITEMS_PATH}")
    print(f"Serving {server.data_path} — edit it and the glasses follow.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()

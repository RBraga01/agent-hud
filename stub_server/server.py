"""A stand-in for the real agent gateway.

Asks the configured feeders for the current list on every request, so what
the glasses show is never stale and there is only one thing to run.

Which feeders it uses comes from the environment. The default is invented
data, which needs no accounts and reveals nothing personal. See the README.

It also takes answers back, at ``POST /tasks/{id}/feedback``. What it is
willing to accept lives in ``policy.py``, deliberately apart from the
plumbing here.

Bound to the loopback address on purpose. It serves whatever the feeders
return, and accepts answers, with no authentication at all, so it must
never be reachable from a network.
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .policy import Policy

TASKS_PATH = "/tasks"
FEEDBACK_SUFFIX = "/feedback"

# The most a feedback request may be. The glasses send a few hundred
# bytes; anything approaching this is not one of them.
MAX_REQUEST_BYTES = 64 * 1024
LOOPBACK_HOST = "127.0.0.1"
DEFAULT_PORT = 8765

DEFAULT_DATA_PATH = Path(__file__).parent / "agents.json"


class _TasksHandler(BaseHTTPRequestHandler):
    """Serves the current task list. The provider is set on the server object."""

    # Set by create_server.
    data_path: Path

    def do_GET(self) -> None:
        if self.path.split("?")[0] != TASKS_PATH:
            self._respond(404, {"error": "not found"})
            return

        try:
            tasks = self.server.policy.tasks()
        except Exception as exc:  # a broken feeder must not take the gateway down
            self._respond(500, {"error": f"feeder failed: {exc}"})
            return

        self._respond(200, {"tasks": tasks})

    def do_POST(self) -> None:
        """Take one answer from the glasses.

        The path names the task; the policy decides everything else. This
        handler only reads the body safely and hands it over.
        """
        path = self.path.split("?")[0]
        if not (path.startswith(TASKS_PATH + "/") and path.endswith(FEEDBACK_SUFFIX)):
            self._respond(404, {"error": "not found"})
            return

        task_id = path[len(TASKS_PATH) + 1 : -len(FEEDBACK_SUFFIX)]
        if not task_id:
            self._respond(404, {"error": "not found"})
            return

        try:
            length = int(self.headers.get("Content-Length", 0))
        except (TypeError, ValueError):
            self._respond(400, {"error": "bad content length"})
            return
        if length > MAX_REQUEST_BYTES:
            self._respond(413, {"error": "request too large"})
            return

        try:
            body = json.loads(self.rfile.read(length) or b"null")
        except (OSError, ValueError):
            self._respond(400, {"error": "body is not JSON"})
            return

        try:
            status, payload = self.server.policy.receive(task_id, body)
        except Exception as exc:  # a broken policy must not take it down either
            self._respond(500, {"error": f"gateway failed: {exc}"})
            return

        self._respond(status, payload)

    def _respond(self, status: int, payload: object) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt: str, *args: object) -> None:
        """Quieter than the default, which prints a line per request."""


class _TasksServer(ThreadingHTTPServer):
    """A server that knows where to get its items."""

    daemon_threads = True

    def __init__(
        self, address: tuple[str, int], provider: Callable[[], list]
    ) -> None:
        self.provider = provider
        self.policy = Policy(provider=provider)
        super().__init__(address, _TasksHandler)


def create_server(
    provider: Callable[[], list], port: int = DEFAULT_PORT
) -> _TasksServer:
    """Build a server bound to loopback.

    Args:
        provider: Called on every request; returns the current list.
        port: Pass 0 to be given a free one.
    """
    return _TasksServer((LOOPBACK_HOST, port), provider)


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
    print(f"Stub gateway on http://{host}:{bound_port}{TASKS_PATH}")
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

"""A stand-in for the real agent gateway.

Asks the configured feeders for the current list on every request, so what
the glasses show is never stale and there is only one thing to run.

Which feeders it uses comes from the environment. The default is invented
data, which needs no accounts and reveals nothing personal. See the README.

It serves the wearer's preferences at ``GET /settings``, and takes answers
back at ``POST /tasks/{id}/feedback``. What it is
willing to accept lives in ``policy.py``, deliberately apart from the
plumbing here.

Bound to the loopback address on purpose. It serves whatever the feeders
return, and accepts answers, with no authentication at all, so it must
never be reachable from a network.
"""

from __future__ import annotations

import json
import os
import time
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from agent_hud.preferences import Preferences, to_payload

from .policy import Policy

TASKS_PATH = "/tasks"
SETTINGS_PATH = "/settings"
CONTROL_PREFIX = "/control/"

CONTROL_DIR = Path(__file__).parent.parent / "control"

# What a browser is allowed to be handed. Anything not listed is not
# served, so a stray file in the folder cannot become a URL.
_CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".webmanifest": "application/manifest+json",
    ".png": "image/png",
}
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
        path = self.path.split("?")[0]

        if path == "/" or path == CONTROL_PREFIX.rstrip("/"):
            self._redirect(CONTROL_PREFIX)
            return

        if path.startswith(CONTROL_PREFIX):
            self._serve_control(path[len(CONTROL_PREFIX):] or "index.html")
            return

        if path == SETTINGS_PATH:
            payload = to_payload(self.server.preferences)
            # What the Control shows about this gateway. The glasses
            # ignore everything here they were not asked about.
            payload["gateway_name"] = self.server.gateway_name
            payload["device_last_seen"] = self.server.device_last_seen
            payload["sources"] = self.server.sources
            self._respond(200, payload)
            return

        if path != TASKS_PATH:
            self._respond(404, {"error": "not found"})
            return

        # Any client asking for the list counts as the device being
        # around. The development gateway has no pairing, so there is
        # nothing better to go on and nothing is claimed beyond "somebody
        # asked recently".
        self.server.device_last_seen = int(time.time())

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

    def _redirect(self, where: str) -> None:
        self.send_response(303)
        self.send_header("Location", where)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _serve_control(self, name: str) -> None:
        """Hand a browser one file from the control folder.

        The name is taken apart and rebuilt rather than joined, so no
        amount of dots or slashes in a request can reach outside the
        folder. Only the handful of types above are served at all.
        """
        safe = Path(name).name  # drops any directory part, and "..​"
        target = CONTROL_DIR / safe
        content_type = _CONTENT_TYPES.get(target.suffix.lower())

        if content_type is None or not target.is_file():
            self._respond(404, {"error": "not found"})
            return

        try:
            body = target.read_bytes()
        except OSError:
            self._respond(404, {"error": "not found"})
            return

        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        # It talks to its own gateway and nothing else. Said out loud so a
        # browser enforces it even if the page is ever changed by mistake.
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self'; "
            "style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
            "connect-src 'self'; base-uri 'none'; form-action 'none'",
        )
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.end_headers()
        self.wfile.write(body)

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
        self,
        address: tuple[str, int],
        provider: Callable[[], list],
        *,
        gateway_name: str = "this machine",
        sources: list[dict] | None = None,
    ) -> None:
        self.provider = provider
        self.policy = Policy(provider=provider)
        # The gateway owns the wearer's preferences; the glasses cache
        # them. The Control app is what changes them, so this development
        # gateway simply serves a fixed, sensible set.
        self.preferences = Preferences(revision=1)
        self.gateway_name = gateway_name
        self.sources = list(sources or [])
        self.device_last_seen: int | None = None
        super().__init__(address, _TasksHandler)


def create_server(
    provider: Callable[[], list],
    port: int = DEFAULT_PORT,
    *,
    gateway_name: str = "this machine",
    sources: list[dict] | None = None,
) -> _TasksServer:
    """Build a server bound to loopback.

    Args:
        provider: Called on every request; returns the current list.
        port: Pass 0 to be given a free one.
    """
    return _TasksServer(
        (LOOPBACK_HOST, port),
        provider,
        gateway_name=gateway_name,
        sources=sources,
    )


def main() -> None:
    """Run the stub until interrupted."""
    from agent_hud.config import load_settings
    from feeders import collect

    settings = load_settings()
    port = int(os.environ.get("AGENT_HUD_PORT", DEFAULT_PORT))
    server = create_server(
        lambda: collect(settings, file_path=DEFAULT_DATA_PATH),
        port=port,
        gateway_name=settings.active_gateway.name,
        sources=[
            {"name": name, "label": name.replace("_", " ").title(), "on": True}
            for name in settings.feeders
        ],
    )
    host, bound_port = server.server_address[:2]
    print(f"Stub gateway on http://{host}:{bound_port}{TASKS_PATH}")
    print(f"Control on      http://{host}:{bound_port}{CONTROL_PREFIX}")
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

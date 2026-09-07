"""A background thread that keeps the polled slice of the store current.

Sources that cannot push -- the ones that read a log file or the SQLite
database or call ``gh`` -- are still polled, but on the gateway's own
clock now, not once per glasses request. One sweep every
``interval`` seconds, whatever the clients are doing.

A sweep that raises leaves the previous slice in place: a scraper that
trips over a half-written file for one tick must not blank the display.
"""

from __future__ import annotations

import threading
from collections.abc import Callable

from .store import TaskStore

DEFAULT_INTERVAL = 5.0

# The slice the refresher owns. `POST /events` writes other keys.
POLL_KEY = "poll"


class Refresher(threading.Thread):
    def __init__(
        self,
        store: TaskStore,
        collect: Callable[[], list[dict]],
        *,
        interval: float = DEFAULT_INTERVAL,
        on_error: Callable[[Exception], None] | None = None,
    ) -> None:
        super().__init__(daemon=True, name="task-refresher")
        self._store = store
        self._collect = collect
        self._interval = max(0.2, float(interval))
        self._on_error = on_error
        self._halt = threading.Event()

    def sweep_once(self) -> bool:
        """Run the feeders once and write the slice. Returns True on success."""
        try:
            tasks = self._collect()
        except Exception as exc:  # a bad sweep must not stop the loop
            if self._on_error is not None:
                self._on_error(exc)
            return False
        self._store.replace(POLL_KEY, list(tasks))
        return True

    def run(self) -> None:
        self.sweep_once()
        while not self._halt.wait(self._interval):
            self.sweep_once()

    def stop(self, timeout: float = 2.0) -> None:
        self._halt.set()
        if self.is_alive():
            self.join(timeout=timeout)


__all__ = ["DEFAULT_INTERVAL", "POLL_KEY", "Refresher"]

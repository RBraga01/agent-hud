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
import time
from collections.abc import Callable
from dataclasses import dataclass

from .store import TaskStore

DEFAULT_INTERVAL = 5.0

# The slice the refresher owns. `POST /events` writes other keys.
POLL_KEY = "poll"


@dataclass(frozen=True)
class SweepHealth:
    """Evidence for the aggregate polling sweep, not per-source completeness."""

    state: str
    last_success_at: float | None
    fresh_until: float | None


class Refresher(threading.Thread):
    def __init__(
        self,
        store: TaskStore,
        collect: Callable[[], list[dict]],
        *,
        interval: float = DEFAULT_INTERVAL,
        on_error: Callable[[Exception], None] | None = None,
        wall_clock: Callable[[], float] = time.time,
        monotonic_clock: Callable[[], float] = time.monotonic,
    ) -> None:
        super().__init__(daemon=True, name="task-refresher")
        self._store = store
        self._collect = collect
        self._interval = max(0.2, float(interval))
        self._on_error = on_error
        self._wall_clock = wall_clock
        self._monotonic_clock = monotonic_clock
        self._sweep_lock = threading.Lock()
        self._last_success_at: float | None = None
        self._last_success_mono: float | None = None
        self._last_attempt_failed = False
        self._halt = threading.Event()

    def health(self) -> SweepHealth:
        """Return aggregate sweep freshness; never infer individual feeder health."""
        with self._sweep_lock:
            last_success = self._last_success_at
            last_mono = self._last_success_mono
            failed = self._last_attempt_failed
            fresh_until = (
                last_success + 2 * self._interval
                if last_success is not None
                else None
            )
            if failed:
                state = "failed"
            elif last_mono is None:
                state = "never_checked"
            elif self._monotonic_clock() > last_mono + 2 * self._interval:
                state = "overdue"
            else:
                state = "healthy"
            return SweepHealth(state, last_success, fresh_until)

    def sweep_once(self) -> bool:
        """Run the feeders once and write the slice. Returns True on success."""
        failure: Exception | None = None
        with self._sweep_lock:
            try:
                tasks = self._collect()
                if not isinstance(tasks, list) or not all(
                    isinstance(task, dict) for task in tasks
                ):
                    raise ValueError("poll collection must be a list of task objects")
                self._store.replace(POLL_KEY, tasks)
            except Exception as exc:  # a bad sweep must not stop the loop
                self._last_attempt_failed = True
                failure = exc
            else:
                self._last_success_at = self._wall_clock()
                self._last_success_mono = self._monotonic_clock()
                self._last_attempt_failed = False
        if failure is not None and self._on_error is not None:
            self._on_error(failure)
        return failure is None

    def run(self) -> None:
        self.sweep_once()
        while not self._halt.wait(self._interval):
            self.sweep_once()

    def stop(self, timeout: float = 2.0) -> None:
        self._halt.set()
        if self.is_alive():
            self.join(timeout=timeout)


__all__ = ["DEFAULT_INTERVAL", "POLL_KEY", "Refresher", "SweepHealth"]

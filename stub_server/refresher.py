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


@dataclass(frozen=True)
class CollectionReport:
    """One aggregate sweep plus independently verified source identities."""

    tasks: list[dict]
    verified_sources: tuple[str, ...]


class Refresher(threading.Thread):
    def __init__(
        self,
        store: TaskStore,
        collect: Callable[[], list[dict] | CollectionReport],
        *,
        interval: float = DEFAULT_INTERVAL,
        on_error: Callable[[Exception], None] | None = None,
        wall_clock: Callable[[], float] = time.time,
        monotonic_clock: Callable[[], float] = time.monotonic,
        sources: tuple[str, ...] = (),
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
        self._sources = tuple(sources)
        self._source_success: dict[str, tuple[float, float]] = {}
        self._source_failed: set[str] = set()
        self._evidence_epoch = 0
        self._verified_store_version: int | None = None
        self._halt = threading.Event()

    def observation(
        self,
    ) -> tuple[int, list[dict], tuple[str, ...], list[dict], int, float]:
        """Read source evidence and stored tasks from one sweep boundary."""
        with self._sweep_lock:
            version, tasks, keys = self._store.raw_snapshot_with_version()
            unverified_store_change = (
                self._verified_store_version is not None
                and version != self._verified_store_version
            )
            now_mono = self._monotonic_clock()
            observed = self._wall_clock()
            health = []
            for name in self._sources:
                success = self._source_success.get(name)
                if name in self._source_failed or unverified_store_change:
                    state = "failed"
                elif success is None:
                    state = "never_checked"
                elif now_mono > success[1] + 2 * self._interval:
                    state = "overdue"
                else:
                    state = "healthy"
                health.append({
                    "name": name,
                    "state": state,
                    "last_success_at": success[0] if success else None,
                    "fresh_until": success[0] + 2 * self._interval if success else None,
                })
            return version, tasks, keys, health, self._evidence_epoch, observed

    def replace_push(self, key: str, tasks: list[dict]) -> tuple[bool, int]:
        """Serialize a pushed slice against poll evidence and snapshots."""
        with self._sweep_lock:
            changed = self._store.replace(key, tasks)
            return changed, self._store.version

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
                result = self._collect()
                report = result if isinstance(result, CollectionReport) else None
                tasks = report.tasks if report is not None else result
                if not isinstance(tasks, list) or not all(
                    isinstance(task, dict) for task in tasks
                ):
                    raise ValueError("poll collection must be a list of task objects")
                verified = set(report.verified_sources) if report else set()
                if report is not None and len(verified) != len(report.verified_sources):
                    raise ValueError("duplicate source evidence")
                if verified - set(self._sources):
                    raise ValueError("unconfigured source evidence")
                self._store.replace(POLL_KEY, tasks)
                self._verified_store_version = self._store.version
            except Exception as exc:  # a bad sweep must not stop the loop
                self._last_attempt_failed = True
                self._source_failed = set(self._sources)
                failure = exc
            else:
                wall = self._wall_clock()
                mono = self._monotonic_clock()
                self._last_success_at = wall
                self._last_success_mono = mono
                self._last_attempt_failed = False
                for name in verified:
                    self._source_success[name] = (wall, mono)
                self._source_failed = set(self._sources) - verified
            self._evidence_epoch += 1
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


__all__ = [
    "DEFAULT_INTERVAL", "POLL_KEY", "CollectionReport", "Refresher", "SweepHealth"
]

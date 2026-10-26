"""The gateway's own view of the task list.

Until now the gateway ran every feeder inside every ``GET /tasks``: each
glasses poll re-tailed the session logs, re-opened the SQLite database,
re-ran ``gh``. The cost scaled with how many clients asked and how often,
not with how often anything changed.

This holds the merged list instead, as named slices. A background
refresher writes the slice for the polled sources on its own schedule,
and ``POST /events`` writes a slice the moment a source pushes -- a hook
that knows something changed does not have to wait for the next poll.
``GET /tasks`` just reads the snapshot.

A slice is a list of task dicts. ``snapshot`` flattens every slice in the
order the slices were first written, and drops a later task whose id was
already seen, so a source that both polls and pushes cannot double a row.
"""

from __future__ import annotations

import threading
from copy import deepcopy


class TaskStore:
    """Named slices of tasks, plus a version that moves on every change."""

    def __init__(self) -> None:
        self._slices: dict[str, list[dict]] = {}
        self._version = 0
        self._lock = threading.Lock()

    @property
    def version(self) -> int:
        with self._lock:
            return self._version

    def replace(self, key: str, tasks: list[dict]) -> bool:
        """Set the slice for ``key``. Returns True if anything changed.

        Identical full content does not move the version. A title, detail
        or offered-action edit matters even if id/revision did not change.
        """
        clean = [deepcopy(t) for t in tasks if isinstance(t, dict)]
        with self._lock:
            if key in self._slices and self._slices[key] == clean:
                return False
            self._slices[key] = clean
            self._version += 1
            return True

    def drop(self, key: str) -> bool:
        """Forget a slice. Returns True if there was one."""
        with self._lock:
            if key not in self._slices:
                return False
            del self._slices[key]
            self._version += 1
            return True

    def snapshot(self) -> list[dict]:
        """The whole list, slices in first-written order, ids deduped."""
        return self.snapshot_with_version()[1]

    def snapshot_with_version(self) -> tuple[int, list[dict], tuple[str, ...]]:
        """Copy the version, projection and slice identities under one lock."""
        version, raw, keys = self.raw_snapshot_with_version()
        out: list[dict] = []
        seen: set[str] = set()
        for task in raw:
            tid = str(task.get("id"))
            if tid in seen:
                continue
            seen.add(tid)
            out.append(task)
        return version, out, keys

    def raw_snapshot_with_version(self) -> tuple[int, list[dict], tuple[str, ...]]:
        """Do not hide duplicate tasks from the companion's validator."""
        with self._lock:
            version = self._version
            keys = tuple(self._slices)
            slices = deepcopy(list(self._slices.values()))
        return version, [task for slice_ in slices for task in slice_], keys


__all__ = ["TaskStore"]

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


def _key_ids(tasks: list[dict]) -> tuple:
    """A cheap fingerprint of a slice, for spotting a no-op replace."""
    return tuple(
        (str(t.get("id")), t.get("revision"), t.get("needs_you"))
        for t in tasks
        if isinstance(t, dict)
    )


class TaskStore:
    """Named slices of tasks, plus a version that moves on every change."""

    def __init__(self) -> None:
        self._slices: dict[str, list[dict]] = {}
        self._prints: dict[str, tuple] = {}
        self._version = 0
        self._lock = threading.Lock()

    @property
    def version(self) -> int:
        with self._lock:
            return self._version

    def replace(self, key: str, tasks: list[dict]) -> bool:
        """Set the slice for ``key``. Returns True if anything changed.

        A replace that fingerprints the same as the slice already there
        does not move the version -- a client polling on the version can
        then tell a real change from a feeder that simply ran again.
        """
        clean = [dict(t) for t in tasks if isinstance(t, dict)]
        fingerprint = _key_ids(clean)
        with self._lock:
            if self._prints.get(key) == fingerprint and key in self._slices:
                return False
            self._slices[key] = clean
            self._prints[key] = fingerprint
            self._version += 1
            return True

    def drop(self, key: str) -> bool:
        """Forget a slice. Returns True if there was one."""
        with self._lock:
            if key not in self._slices:
                return False
            del self._slices[key]
            self._prints.pop(key, None)
            self._version += 1
            return True

    def snapshot(self) -> list[dict]:
        """The whole list, slices in first-written order, ids deduped."""
        with self._lock:
            slices = [list(v) for v in self._slices.values()]
        out: list[dict] = []
        seen: set[str] = set()
        for slice_ in slices:
            for task in slice_:
                tid = str(task.get("id"))
                if tid in seen:
                    continue
                seen.add(tid)
                out.append(dict(task))
        return out


__all__ = ["TaskStore"]

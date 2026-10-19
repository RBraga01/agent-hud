"""What the gateway is willing to accept, and what it does about it.

The glasses render actions; they do not authorise them. An agent cannot
put an executable button on someone's face by naming one, because the
gateway checks every incoming answer against the actions *it* would have
offered for that task, not against whatever the request claims.

Checks run under one lock, in order, and the order matters:

1. **Have I already handled this request?** An identical retry after an
   uncertain network gets the first answer back. Changed content conflicts.
2. **Is this still the task they were looking at?** A revision behind the
   current one is refused, so nobody approves a description that changed
   while they were reading it.
3. **Would I have offered this action?** Anything else is refused.

This is the development gateway. It keeps its state in memory and forgets
everything when it stops, which is the right amount of machinery for
something whose job is to let you run the app without accounts.
"""

from __future__ import annotations

import json
import re
import threading
from collections.abc import Callable
from dataclasses import dataclass, field

# How many handled requests to remember. Enough that a retry minutes
# later is still recognised, small enough to bound the memory.
MAX_REMEMBERED = 512

MAX_TEXT = 2000
_IDENTIFIER = re.compile(r"[A-Za-z0-9._:-]{1,128}\Z")


@dataclass
class _Handled:
    """The answer given to a request, kept so a retry gets the same one."""

    status: int
    payload: dict
    content: tuple[str, str]


@dataclass
class Policy:
    """Decides what the gateway accepts, and remembers what it did.

    Args:
        provider: Called for the current task list, exactly as the GET
            handler calls it. The policy always checks against fresh
            state rather than anything the client sent.
    """

    provider: Callable[[], list[dict]]
    _handled: dict[str, _Handled] = field(default_factory=dict)
    _resolved: dict[str, int] = field(default_factory=dict)
    _lock: threading.RLock = field(default_factory=threading.RLock, repr=False)

    # -- reading --------------------------------------------------------

    def tasks(self) -> list[dict]:
        """The current list, with anything already answered marked done.

        The gateway owns task state, so an answered task stops needing
        you here rather than in the feeder that reported it. Its revision
        moves at the same time, which is what tells a glasses client
        holding the old one that it is looking at something out of date.
        """
        with self._lock:
            out = []
            for task in self.provider():
                task = dict(task)
                answered = self._resolved.get(str(task.get("id")))
                if answered is not None and answered >= int(task.get("revision", 0)):
                    task["revision"] = answered + 1
                    task["needs_you"] = False
                    task["summary"] = "answered"
                    task["actions"] = {}
                out.append(task)
            return out

    def find_public(self, task_id: str) -> dict | None:
        """One task as this gateway currently sees it, or None."""
        return self._find(task_id)

    # -- writing --------------------------------------------------------

    def receive(self, task_id: str, body: object) -> tuple[int, dict]:
        """Take one answer. Returns the status and payload to send back."""
        if not isinstance(body, dict):
            return 400, {"error": "body must be an object"}

        request_id = body.get("request_id")
        if not isinstance(request_id, str) or not _IDENTIFIER.fullmatch(request_id):
            return 400, {"error": "request_id is required"}

        try:
            content = (task_id, json.dumps(body, sort_keys=True, allow_nan=False))
        except (TypeError, ValueError):
            return 400, {"error": "body must be valid JSON"}

        with self._lock:
            # Lookup, judgment, effect and registration are one critical section.
            seen = self._handled.get(request_id)
            if seen is not None:
                if seen.content != content:
                    return 409, {
                        "error": "request_id content changed",
                        "code": "id_conflict",
                    }
                return seen.status, dict(seen.payload, replayed=True)

            status, payload = self._judge(task_id, body)

            # A 5xx/unknown result is not a decision: allow a later retry.
            if status < 500:
                self._remember(request_id, status, payload, content)
            return status, payload

    def _judge(self, task_id: str, body: dict) -> tuple[int, dict]:
        if not _IDENTIFIER.fullmatch(task_id):
            return 400, {"error": "task_id is invalid"}
        task = self._find(task_id)
        if task is None:
            return 404, {"error": "no such task"}

        revision = body.get("revision")
        if (
            type(revision) is not int
            or not 0 <= revision <= 2**53 - 1
        ):
            return 400, {"error": "revision must be a number"}

        # 2. Still the same task they were looking at?
        current = int(task.get("revision", 0))
        if revision != current:
            return 409, {
                "status": "stale",
                "error": "this task has changed since you looked at it",
                "revision": current,
            }

        kind = body.get("type")
        if kind == "action":
            return self._judge_action(task, body)
        if kind == "message":
            return self._judge_message(task, body)
        return 400, {"error": "type must be action or message"}

    def _judge_action(self, task: dict, body: dict) -> tuple[int, dict]:
        action_id = body.get("action_id")
        if not isinstance(action_id, str) or not _IDENTIFIER.fullmatch(action_id):
            return 400, {"error": "action_id is required"}

        # 3. Would this gateway have offered it? Checked against our own
        # task, never against anything the request claims.
        if action_id not in self._offered(task):
            return 422, {"error": f"this task does not offer {action_id!r}"}

        self._resolve(task)
        return 200, {"status": "accepted", "action_id": action_id}

    def _judge_message(self, task: dict, body: dict) -> tuple[int, dict]:
        text = body.get("text")
        if not isinstance(text, str) or not text.strip():
            return 400, {"error": "text is required"}
        self._resolve(task)
        return 200, {"status": "accepted", "characters": len(text[:MAX_TEXT])}

    # -- helpers --------------------------------------------------------

    def _find(self, task_id: str) -> dict | None:
        """The task as *this gateway* currently sees it.

        Deliberately the resolved view, not the raw feeder list. Judging
        against the raw list would let a second request with a fresh id
        answer a task that has already been answered, because the feeder
        still reports the old revision until its own source catches up.
        """
        for task in self.tasks():
            if str(task.get("id")) == task_id:
                return task
        return None

    @staticmethod
    def _offered(task: dict) -> set[str]:
        """The action ids this gateway would put on the display."""
        actions = task.get("actions")
        if not isinstance(actions, dict):
            return set()
        offered = set()
        for slot in ("primary", "secondary"):
            action = actions.get(slot)
            if isinstance(action, dict) and isinstance(action.get("id"), str):
                offered.add(action["id"])
        return offered

    def _resolve(self, task: dict) -> None:
        self._resolved[str(task.get("id"))] = int(task.get("revision", 0))

    def _remember(
        self, request_id: str, status: int, payload: dict, content: tuple[str, str]
    ) -> None:
        if len(self._handled) >= MAX_REMEMBERED:
            # Drop the oldest. Python dicts keep insertion order, so the
            # first key is the one least recently added.
            self._handled.pop(next(iter(self._handled)))
        self._handled[request_id] = _Handled(
            status=status, payload=dict(payload), content=content
        )

"""Local canonical compatibility API over the existing development policy.

No network endpoint or authentication bypass. Its owner must retain this object
for the declared session. Replay protection is bounded and in-memory only.
"""

import re
from threading import RLock

from .policy import MAX_REMEMBERED, Policy

_ID = re.compile(r"[A-Za-z0-9._:-]{1,128}\Z")
_FIELDS = {"decision_id", "task_id", "revision", "action_id"}


class CanonicalGateway:
    def __init__(self, policy: Policy):
        self.policy = policy
        self._seen: dict[str, tuple[dict, dict]] = {}
        self._lock = RLock()

    def receive(self, decision: object) -> dict:
        with self._lock:
            return self._receive(decision)

    def _receive(self, decision: object) -> dict:
        if not isinstance(decision, dict):
            return {"status": "ERROR", "reason": "invalid_envelope"}
        result = {k: decision.get(k) for k in ("decision_id", "task_id", "revision")}
        result.update(status="ERROR", reason="invalid_envelope")
        if set(decision) != _FIELDS:
            return result
        if any(
            not isinstance(decision[k], str) or not _ID.fullmatch(decision[k])
            for k in ("decision_id", "task_id", "action_id")
        ):
            return result
        if (
            type(decision["revision"]) is not int
            or not 0 <= decision["revision"] <= 2**53 - 1
        ):
            return result
        seen = self._seen.get(decision["decision_id"])
        if seen:
            original, previous = seen
            if original != decision:
                return dict(result, reason="id_conflict")
            return {
                **previous,
                "status": "DUPLICATE",
                "original_status": previous["status"],
            }
        try:
            code, _ = self.policy.receive(
                decision["task_id"],
                {
                    "type": "action",
                    "request_id": "canonical:" + decision["decision_id"],
                    "revision": decision["revision"],
                    "action_id": decision["action_id"],
                },
            )
        except Exception:
            return dict(result, reason="delivery_unknown")
        status = {200: "ACCEPTED", 409: "STALE", 422: "INVALID_ACTION"}.get(
            code, "ERROR"
        )
        result = {k: decision[k] for k in ("decision_id", "task_id", "revision")}
        result["status"] = status
        if status != "ERROR":
            if len(self._seen) >= MAX_REMEMBERED:
                self._seen.pop(next(iter(self._seen)))
            self._seen[decision["decision_id"]] = (dict(decision), dict(result))
        return result

"""Canonical mock/host framing. No BLE connection or live-agent integration."""

import json
import uuid


class CanonicalSession:
    """Create a fresh ID namespace for every device VM boot/reconnect."""

    def __init__(self):
        self.session_id = uuid.uuid4().hex

    def request(self, task, *, title, short_context):
        body = {
            "session_id": self.session_id,
            "task": task,
            "presentation": {"title": title, "short_context": short_context},
        }
        return (
            b"\x12"
            + json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode()
        )

    @staticmethod
    def result(decision, status, **details):
        body = {key: decision[key] for key in ("decision_id", "task_id", "revision")}
        body.update(status=status, **details)
        return b"\x13" + json.dumps(body, separators=(",", ":")).encode()

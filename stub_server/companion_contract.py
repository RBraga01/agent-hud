"""Cross-field checks that JSON Schema cannot express for companion snapshots.

The future HTTP handler must run these against one synchronized observation
before returning a snapshot. This module does not create an endpoint or confer
any mobile decision permission.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta

_ID = re.compile(r"[A-Za-z0-9._:-]{1,128}\Z")


def normalize_tasks(tasks: list[dict]) -> list[dict]:
    """Strictly map the legacy glasses projection into the approved v1 shape."""
    result = []
    seen: set[str] = set()
    for task in tasks:
        if not isinstance(task, dict):
            raise ValueError("task is not an object")
        task_id = task.get("id")
        revision = task.get("revision")
        if (not isinstance(task_id, str) or not _ID.fullmatch(task_id)
                or task_id in seen or type(revision) is not int
                or not 0 <= revision <= 2**53 - 1):
            raise ValueError("invalid or duplicate task identity")
        seen.add(task_id)
        for field in ("source", "title", "summary", "detail"):
            value = task.get(field)
            if not isinstance(value, str) or (
                field in ("source", "title") and not value
            ):
                raise ValueError("invalid task content")
        if type(task.get("needs_you")) is not bool:
            raise ValueError("invalid task urgency")
        legacy_actions = task.get("actions", {})
        if not isinstance(legacy_actions, dict) or set(legacy_actions) - {
            "primary", "secondary"
        }:
            raise ValueError("invalid task actions")
        actions = []
        action_ids: set[str] = set()
        for slot in ("primary", "secondary"):
            if slot not in legacy_actions:
                continue
            action = legacy_actions[slot]
            if not isinstance(action, dict):
                raise ValueError("invalid task action")
            action_id = action.get("id")
            label = action.get("label")
            if (not isinstance(action_id, str) or not _ID.fullmatch(action_id)
                    or action_id in action_ids or not isinstance(label, str)
                    or not 1 <= len(label) <= 16):
                raise ValueError("invalid or duplicate task action")
            action_ids.add(action_id)
            actions.append({"action_id": action_id, "label": label})
        result.append({
            "task_id": task_id,
            "revision": revision,
            "source": task["source"],
            "title": task["title"],
            "summary": task["summary"],
            "detail": task["detail"],
            "needs_you": task["needs_you"],
            "actions": actions,
        })
    return result


def _instant(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, TypeError, ValueError) as exc:
        raise ValueError("invalid snapshot timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("snapshot timestamp must have an offset")
    return parsed


def validate_snapshot_semantics(snapshot: dict) -> None:
    """Reject impossible freshness or duplicate identities; return on success."""
    observed = _instant(snapshot["observed_at"])
    sources = snapshot["source_health"]
    if snapshot["complete"]:
        if not sources:
            raise ValueError("complete snapshot has no sources")
        for source in sources:
            if source["state"] != "healthy":
                raise ValueError("complete snapshot has an unhealthy source")
            last = _instant(source["last_success_at"])
            until = _instant(source["fresh_until"])
            if not last <= observed <= until:
                raise ValueError("source freshness is outside observation")

    source_names = [source["name"] for source in sources]
    if len(source_names) != len(set(source_names)):
        raise ValueError("duplicate source identity")

    task_ids = [task["task_id"] for task in snapshot["tasks"]]
    if len(task_ids) != len(set(task_ids)):
        raise ValueError("duplicate task identity")
    for task in snapshot["tasks"]:
        action_ids = [action["action_id"] for action in task["actions"]]
        if len(action_ids) != len(set(action_ids)):
            raise ValueError("duplicate action identity")

    device = snapshot["selected_device"]
    if device is None:
        return
    if (device["health"] in {"healthy", "unavailable"}
            and device["evidence"] not in {
                "verified_link", "verified_device_heartbeat"
            }):
        raise ValueError("device lacks independent evidence")
    if device["health"] == "healthy":
        last = _instant(device["last_verified_link_at"])
        until = _instant(device["presence_valid_until"])
        if not last <= observed <= until:
            raise ValueError("device freshness is outside observation")
    elif device["health"] == "unavailable":
        last = _instant(device["last_verified_link_at"])
        absence = _instant(device["absence_started_at"])
        valid_until = device["presence_valid_until"]
        if (device["failed_observations"] < 2 or not last <= absence
                or observed - absence < timedelta(seconds=60)
                or (valid_until is not None
                    and _instant(valid_until) >= observed)):
            raise ValueError("device absence threshold is unproven")


__all__ = ["normalize_tasks", "validate_snapshot_semantics"]

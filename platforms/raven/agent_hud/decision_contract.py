"""Raven's canonical boundary; normative definitions live under core/."""

from collections.abc import Callable

from .feedback import Feedback, new_request_id
from .navigation import Nav, Screen
from .tasks import Task, find_task


def current_observations(previous: list[Task], incoming: list[Task]) -> list[Task]:
    """Ignore revision rollback, while respecting removals from the fresh list."""
    known = {task.id: task for task in previous}
    return [
        known[task.id]
        if task.id in known and known[task.id].revision > task.revision
        else task
        for task in incoming
    ]


def prepare_feedback(
    nav: Nav,
    tasks: list[Task],
    allocate: Callable[[], str] = new_request_id,
) -> Feedback | None:
    """Freeze a valid observed action only in the separate confirmation state."""
    if nav.screen is not Screen.CONFIRMATION:
        return None
    task = find_task(tasks, nav.task_id)
    if task is None or task.revision != nav.revision:
        return None
    if not any(a and a.id == nav.action_id for a in (task.primary, task.secondary)):
        return None
    return Feedback(
        task_id=task.id,
        revision=nav.revision,
        action_id=nav.action_id,
        request_id=allocate(),
    )


def canonical_decision(feedback: Feedback) -> dict:
    """Keep the legacy HTTP body intact; expose canonical names explicitly."""
    if feedback.action_id is None or feedback.text is not None:
        raise ValueError("M0 only covers offered action decisions")
    return {
        "decision_id": feedback.request_id,
        "task_id": feedback.task_id,
        "revision": feedback.revision,
        "action_id": feedback.action_id,
    }


def correlated_status(result: object, decision: dict) -> str | None:
    """An unmatched or malformed acknowledgement is never an acceptance."""
    if not isinstance(result, dict):
        return None
    if type(result.get("revision")) is not int:
        return None
    if any(
        result.get(key) != decision[key]
        for key in ("decision_id", "task_id", "revision")
    ):
        return None
    status = result.get("status")
    if status == "DUPLICATE":
        original = result.get("original_status")
        return original if original in ("ACCEPTED", "STALE", "INVALID_ACTION") else None
    if status in ("ACCEPTED", "STALE", "INVALID_ACTION", "ERROR"):
        return status
    return None

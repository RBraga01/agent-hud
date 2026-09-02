"""The task contract between the gateway and the glasses.

The glasses know nothing about Claude, Codex, GitHub or any other tool.
They receive a list of tasks and draw them. Every tool-specific detail is
resolved on the gateway before it gets here.

A task carries what each screen needs and nothing more:

    task list      source + summary
    task detail    source + title + detail
    action menu    title + primary + secondary

It also carries a ``revision``. That is what makes it safe to act on: the
gateway refuses feedback quoting a revision it has already moved past, so
the wearer can never approve a version of a task that no longer exists.

Parsing is strict on purpose. An entry that does not match the contract
is dropped rather than guessed at, because guessing would either hide
work from you or invent work that is not there. Dropping surfaces a
broken gateway quickly; guessing hides it.

It is also bounded on purpose. The response is otherwise unlimited, and
on a wearable an oversized list or a single entry carrying a page of text
could make the display unusable. A capped or shortened list is not a whole
list, so it carries the same incomplete signal a discarded entry does.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# Caps on what one response may contain. Excess tasks are dropped; text
# over length is cut with a trailing "...". Both mark the payload
# incomplete, which is what lights the amber marker.
MAX_TASKS = 100
MAX_SOURCE = 24
MAX_TITLE = 64
MAX_SUMMARY = 96
MAX_DETAIL = 2048
MAX_LABEL = 16

_ELLIPSIS = "..."

# Text fields that must be present and non-empty for a task to be usable.
_REQUIRED_TEXT = ("id", "source", "title", "summary")


@dataclass(frozen=True)
class Action:
    """Something the gateway is willing to accept for a task.

    Attributes:
        id: What gets sent back. The glasses never invent one.
        label: The word drawn on the button, written by the gateway.
    """

    id: str
    label: str


@dataclass(frozen=True)
class Task:
    """One thing the gateway is reporting on.

    Attributes:
        id: Stable identifier, used to tell tasks apart between refreshes.
        revision: Which version of this task is on screen. Sent back with
            any feedback so the gateway can refuse a stale answer.
        source: Which tool it came from, drawn at the top of a row.
        title: Short name of the work itself.
        summary: One line for the list. May repeat part of the title.
        detail: The full text, for the detail screen. May be empty.
        needs_you: True when this task is waiting on the wearer.
        primary: The main action offered, or None.
        secondary: The other action offered, or None.
    """

    id: str
    revision: int
    source: str
    title: str
    summary: str
    detail: str
    needs_you: bool
    primary: Action | None = None
    secondary: Action | None = None

    @property
    def has_actions(self) -> bool:
        """True when there is anything to open the action menu for."""
        return self.primary is not None or self.secondary is not None


@dataclass(frozen=True)
class ParsedTasks:
    """What a gateway response turned out to contain.

    Attributes:
        tasks: The entries that matched the contract.
        dropped: How many entries did not match, or were past the task
            cap, and were discarded.
        truncated: How many kept entries lost something — text cut to fit,
            or an action that could not be read. They are on screen but
            not in full.
        valid: False when the payload was not a list of tasks at all.
            An invalid payload means the gateway cannot be trusted, which
            is a different thing from it having nothing to report.
    """

    tasks: list[Task] = field(default_factory=list)
    dropped: int = 0
    truncated: int = 0
    valid: bool = True


def _truncate(text: str, limit: int) -> tuple[str, bool]:
    """Hard-cap a drawn string. Returns the text and whether it was cut.

    A cut string is exactly ``limit`` characters, the last three a "...".
    """
    if len(text) <= limit:
        return text, False
    return text[: limit - len(_ELLIPSIS)] + _ELLIPSIS, True


def _parse_action(raw: Any) -> tuple[Action | None, bool]:
    """Return (Action, was_shortened), or (None, True) when unreadable.

    An action that cannot be read is simply not offered. It never takes
    the whole task down with it: the wearer still needs to know the work
    exists, even if this display cannot act on it.
    """
    if not isinstance(raw, dict):
        return None, True

    action_id = raw.get("id")
    label = raw.get("label")
    if not isinstance(action_id, str) or not action_id:
        return None, True
    if not isinstance(label, str) or not label:
        return None, True

    label, cut = _truncate(label, MAX_LABEL)
    return Action(id=action_id, label=label), cut


def _parse_revision(raw: Any) -> int | None:
    """A whole, non-negative number. Booleans are not numbers here.

    In Python ``True`` is an ``int``, so a payload sending ``true`` where a
    revision belongs would otherwise be read as revision 1 and quietly
    pass every freshness check.
    """
    if isinstance(raw, bool) or not isinstance(raw, int) or raw < 0:
        return None
    return raw


def _parse_task(raw: Any) -> tuple[Task, bool] | None:
    """Return (Task, was_shortened), or None when it fails the contract."""
    if not isinstance(raw, dict):
        return None

    for name in _REQUIRED_TEXT:
        value = raw.get(name)
        if not isinstance(value, str) or not value:
            return None

    detail = raw.get("detail")
    if not isinstance(detail, str):
        return None

    needs_you = raw.get("needs_you")
    # Checked against bool specifically: in Python a plain 1 is an int, not
    # a bool, and the string "false" is truthy. Neither may slip through.
    if not isinstance(needs_you, bool):
        return None

    revision = _parse_revision(raw.get("revision"))
    if revision is None:
        return None

    source, source_cut = _truncate(raw["source"], MAX_SOURCE)
    title, title_cut = _truncate(raw["title"], MAX_TITLE)
    summary, summary_cut = _truncate(raw["summary"], MAX_SUMMARY)
    detail, detail_cut = _truncate(detail, MAX_DETAIL)

    actions = raw.get("actions")
    if actions is None:
        primary = secondary = None
        actions_cut = False
    elif isinstance(actions, dict):
        primary, primary_cut = (
            _parse_action(actions["primary"]) if "primary" in actions else (None, False)
        )
        secondary, secondary_cut = (
            _parse_action(actions["secondary"])
            if "secondary" in actions
            else (None, False)
        )
        actions_cut = primary_cut or secondary_cut
    else:
        # An actions block that is not a block at all. Offer nothing, and
        # say so, rather than guessing at what was meant.
        primary = secondary = None
        actions_cut = True

    task = Task(
        id=raw["id"],
        revision=revision,
        source=source,
        title=title,
        summary=summary,
        detail=detail,
        needs_you=needs_you,
        primary=primary,
        secondary=secondary,
    )
    shortened = (
        source_cut or title_cut or summary_cut or detail_cut or actions_cut
    )
    return task, shortened


def parse_tasks(payload: Any) -> ParsedTasks:
    """Read a gateway response, keeping empty and broken clearly apart.

    Never raises.
    """
    if not isinstance(payload, dict):
        return ParsedTasks(valid=False)

    raw_tasks = payload.get("tasks")
    if not isinstance(raw_tasks, list):
        return ParsedTasks(valid=False)

    dropped = 0
    if len(raw_tasks) > MAX_TASKS:
        dropped += len(raw_tasks) - MAX_TASKS
        raw_tasks = raw_tasks[:MAX_TASKS]

    tasks, truncated = [], 0
    for raw in raw_tasks:
        parsed = _parse_task(raw)
        if parsed is None:
            dropped += 1
            continue
        task, shortened = parsed
        tasks.append(task)
        if shortened:
            truncated += 1
    return ParsedTasks(
        tasks=tasks, dropped=dropped, truncated=truncated, valid=True
    )


def needs_you_count(tasks: list[Task]) -> int:
    """How many tasks are waiting on the wearer. This is the number shown."""
    return sum(1 for task in tasks if task.needs_you)


def find_task(tasks: list[Task], task_id: str | None) -> Task | None:
    """The task with that id, or None. Used to reconcile what is on screen."""
    if task_id is None:
        return None
    for task in tasks:
        if task.id == task_id:
            return task
    return None

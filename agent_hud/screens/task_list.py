"""Screen 3 — what is waiting on you.

One row per task: where it came from, and one line about it. Nothing
more. The list is for choosing which thing to look at, not for reading;
that is what the detail screen is for.

Rows past the first page are counted rather than shown. A count is one
glance; a scrolling list is sustained attention on moving text, which is
tiring on a headset and buys nothing here.
"""

from __future__ import annotations

from collections.abc import Callable

from raven_framework.components.vertical_container import VerticalContainer

from ..tasks import Task
from . import parts
from . import style as s

CARD_WIDTH = 470
ROW_WIDTH = CARD_WIDTH - s.CARD_MARGIN * 2


def build_task_list(
    tasks: list[Task],
    *,
    page: int = 0,
    on_select: Callable[[str], None],
) -> VerticalContainer:
    """The card listing what needs the wearer.

    Args:
        tasks: Only the ones that need you. Ordering is the gateway's.
        page: Which page of rows to show.
        on_select: Called with a task id when a row is activated. The row
            is a real button, so this fires on the wearer's double blink
            or dwell, never on gaze alone.
    """
    card = parts.card(CARD_WIDTH)
    card.add(parts.title("Needs you", width=ROW_WIDTH))

    start = page * s.ROWS_PER_PAGE
    shown = tasks[start : start + s.ROWS_PER_PAGE]
    for task in shown:
        card.add(
            parts.row_button(
                task.source,
                task.summary,
                lambda task_id=task.id: on_select(task_id),
                width=ROW_WIDTH,
            )
        )

    remaining = len(tasks) - (start + len(shown))
    if remaining > 0:
        card.add(parts.small(f"+{remaining} more", width=ROW_WIDTH))

    return card

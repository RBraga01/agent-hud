"""Screen 4 — understand the task before doing anything about it.

Where it came from, what it is, and the gateway's own words about it.
Opening this screen never implies intent to act: the way on is a separate,
deliberate press.

Long text is paged rather than scrolled. One page is one glance; a moving
column of text asks the wearer to hold their eyes on it, which is tiring
and buys nothing when the text is short enough to page through.
"""

from __future__ import annotations

from collections.abc import Callable

from raven_framework.components.vertical_container import VerticalContainer

from ..navigation import detail_page, page_count
from ..tasks import Task
from . import parts
from . import style as s

CARD_WIDTH = 500
INNER_WIDTH = CARD_WIDTH - s.CARD_MARGIN * 2


def build_task_detail(
    task: Task,
    *,
    page: int = 0,
    stale: bool = False,
    on_back: Callable[[], None],
    on_take_action: Callable[[], None] | None = None,
    on_scroll_up: Callable[[], None] | None = None,
    on_scroll_down: Callable[[], None] | None = None,
) -> VerticalContainer:
    """The card for one task.

    Args:
        task: What to show.
        page: Which page of the detail text.
        stale: True when the wearer was sent back here because the task
            changed under a pending confirmation. Says so, plainly.
        on_take_action: Omit, or pass None, when the gateway offered no
            actions. The button is then not drawn at all rather than
            drawn and refusing, because a button that does nothing is a
            promise the display cannot keep.
    """
    card = parts.card(CARD_WIDTH, spacing=10)

    card.add(parts.label(task.source, width=INNER_WIDTH))
    card.add(parts.title(task.title, width=INNER_WIDTH))
    card.add(parts.rule(INNER_WIDTH))

    if stale:
        card.add(
            parts.small(
                "This changed while you were deciding. Read it again.",
                width=INNER_WIDTH,
                align="left",
            )
        )

    text = detail_page(task, page)
    card.add(parts.body(text or "Nothing more to say about this one.", INNER_WIDTH))

    pages = page_count(task)
    if pages > 1:
        card.add(parts.small(f"{page + 1} of {pages}", width=INNER_WIDTH))

    buttons = [parts.secondary_button("Back", on_back, width=140)]

    # Paging controls only appear when there is somewhere to page to.
    if pages > 1 and page > 0 and on_scroll_up is not None:
        buttons.append(parts.secondary_button("Up", on_scroll_up, width=100))
    if pages > 1 and page < pages - 1 and on_scroll_down is not None:
        buttons.append(parts.secondary_button("More", on_scroll_down, width=110))

    if on_take_action is not None:
        buttons.append(
            parts.primary_button("Take action", on_take_action, width=190)
        )

    card.add(parts.button_row(INNER_WIDTH, buttons))
    return card


__all__ = ["CARD_WIDTH", "build_task_detail"]

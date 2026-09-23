"""Screen 6 — the last stop before anything leaves the glasses.

Every action, whatever it is and wherever it was chosen, ends up here.
One screen, one shape, every time, so the moment of committing always
looks the same and is never mistaken for a step along the way.

Only the OK button sends. Reaching this screen does not, and neither did
choosing the action that led here.
"""

from __future__ import annotations

import os
from collections.abc import Callable

from raven_framework.components.horizontal_container import HorizontalContainer
from raven_framework.components.icon import Icon
from raven_framework.components.text_box import TextBox
from raven_framework.components.vertical_container import VerticalContainer

from ..tasks import Action, Task
from . import parts
from . import style as s

CARD_WIDTH = 470
INNER_WIDTH = CARD_WIDTH - s.CARD_MARGIN * 2
ICON_SIZE = 34


def build_confirmation(
    task: Task,
    action: Action,
    *,
    on_cancel: Callable[[], None],
    on_ok: Callable[[], None],
) -> VerticalContainer:
    """Ask once, plainly, and name exactly what will happen."""
    card = parts.card(CARD_WIDTH, spacing=10)

    card.add(parts.label(task.source, width=INNER_WIDTH))
    card.add(parts.title(task.title, width=INNER_WIDTH))

    # The chosen action, in its own box, so it reads as the subject of the
    # question rather than as another line of the task description.
    chosen = HorizontalContainer(
        width=INNER_WIDTH,
        inner_margin=(18, 16, 18, 16),
        spacing=14,
        corner_radius=s.ROW_RADIUS,
        border_width=s.BORDER,
        border_color=s.ACCENT,
        background_color=s.TRANSPARENT,
        **s.outline(),
    )
    chosen.add(
        Icon(
            is_square=True,
            background_image_path=os.path.join(
                parts._ASSETS, "actions", "check.png"
            ),
            size=ICON_SIZE,
            enable_click=False,
        )
    )
    words = VerticalContainer(width=INNER_WIDTH - ICON_SIZE - 50, spacing=2)
    words.add(
        TextBox(
            "Selected action",
            font_size=s.SMALL_SIZE,
            font_weight=s.MEDIUM,
            text_color=s.TEXT_DIM,
            width=INNER_WIDTH - ICON_SIZE - 50,
            wrap_words=False,
        )
    )
    words.add(
        TextBox(
            action.label.upper(),
            font_size=s.ROW_TITLE_SIZE,
            font_weight=s.HEAVY,
            text_color=s.TEXT,
            width=INNER_WIDTH - ICON_SIZE - 50,
            wrap_words=False,
        )
    )
    chosen.add(words)
    card.add(chosen)

    card.add(
        parts.button_row(
            INNER_WIDTH,
            [
                parts.secondary_button("Cancel", on_cancel, width=160),
                parts.primary_button("OK", on_ok, width=160),
            ],
        )
    )
    return card


__all__ = ["CARD_WIDTH", "build_confirmation"]

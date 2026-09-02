"""Screen 2 — how many things are waiting.

A number and two words. This is the screen the wearer sees most often
after the resting dot, and it exists to be understood without being read:
the count is large enough to take in at a glance, and everything else on
the display is absent.

Activating it opens the list. Looking at it does not.
"""

from __future__ import annotations

from collections.abc import Callable

from raven_framework.components.button import Button
from raven_framework.components.container import Container
from raven_framework.components.text_box import TextBox
from raven_framework.components.vertical_container import VerticalContainer

from . import style as s

CARD_SIZE = 190
RING_SIZE = 108
LABEL_HEIGHT = 22


def build_attention(count: int, *, on_open: Callable[[], None]) -> Button:
    """The count card.

    The whole card is the button. A small target would be unfair to aim
    at with gaze, and there is nothing else on this screen to hit by
    mistake.

    The contents are placed by coordinate rather than stacked. A stacking
    container centres nothing, so getting a circle into the middle of a
    square by nudging margins is guesswork that breaks the moment a font
    or a size changes.
    """
    ring = VerticalContainer(
        width=RING_SIZE,
        height=RING_SIZE,
        corner_radius=RING_SIZE // 2,
        border_width=s.BORDER,
        border_color=s.ACCENT,
        background_color=s.TRANSPARENT,
        inner_margin=(0, (RING_SIZE - 52) // 2, 0, 0),
        **s.outline(),
    )
    ring.add(
        TextBox(
            str(count),
            font_size=44,
            font_weight=s.HEAVY,
            text_color=s.TEXT,
            alignment="center",
            width=RING_SIZE,
            wrap_words=False,
        )
    )

    caption = TextBox(
        s.label_text("Needs you"),
        font_size=s.LABEL_SIZE,
        font_weight=s.HEAVY,
        text_color=s.ACCENT,
        alignment="center",
        width=CARD_SIZE,
        height=LABEL_HEIGHT,
        wrap_words=False,
    )

    # Ring, then the caption under it, as one centred block.
    block_height = RING_SIZE + 10 + LABEL_HEIGHT
    top = (CARD_SIZE - block_height) // 2

    inner = Container(
        width=CARD_SIZE, height=CARD_SIZE, background_color=s.TRANSPARENT
    )
    inner.add(ring, (CARD_SIZE - RING_SIZE) // 2, top)
    inner.add(caption, 0, top + RING_SIZE + 10)

    card = Button(
        width=CARD_SIZE,
        height=CARD_SIZE,
        content_widget=inner,
        background_color=s.TRANSPARENT,
        corner_radius=s.CARD_RADIUS,
        outline_width=s.BORDER,
        outline_color=s.ACCENT,
        scale_by=0.0,
        **s.outline(),
    )
    card.on_clicked(on_open)
    return card


__all__ = ["CARD_SIZE", "build_attention"]

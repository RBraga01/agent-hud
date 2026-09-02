"""Screen 5 — choose what to do, without doing it.

The geometry is fixed and never rearranges:

    top     Audio
    left    the primary action
    right   the secondary action
    bottom  Cancel
    centre  which task this is, and not something you can press

Fixed because the wearer aims with their eyes. If "Approve" were
sometimes left and sometimes right, every visit would need reading before
aiming. It never moves, so eventually it needs neither.

An action the gateway did not offer leaves its position empty. The
display never fills a gap with something it invented, and never moves the
other action across to tidy up the hole.

Choosing here does not send anything. It opens the confirmation screen.
"""

from __future__ import annotations

import os
from collections.abc import Callable

from raven_framework.components.button import Button
from raven_framework.components.container import Container
from raven_framework.components.icon import Icon
from raven_framework.components.text_box import TextBox
from raven_framework.components.vertical_container import VerticalContainer

from ..tasks import Action, Task
from . import parts
from . import style as s

WIDTH = 560
HEIGHT = 470

CENTRE_SIZE = 152
SATELLITE_W = 130
SATELLITE_H = 96
ICON_SIZE = 30

_ACTIONS_DIR = os.path.join(parts._ASSETS, "actions")


def _satellite(
    text: str, icon_name: str, on_click: Callable[[], None] | None
) -> Button:
    """One of the four positions: a mark and a word, in a rounded box."""
    icon = Icon(
        is_square=True,
        background_image_path=os.path.join(_ACTIONS_DIR, icon_name),
        size=ICON_SIZE,
        enable_click=False,
    )
    caption = TextBox(
        s.label_text(text),
        font_size=s.LABEL_SIZE,
        font_weight=s.HEAVY,
        text_color=s.TEXT,
        alignment="center",
        width=SATELLITE_W,
        wrap_words=False,
    )

    # Placed by coordinate: a stacking container centres nothing, and
    # nudging margins to fake it breaks whenever a label changes length.
    inner = Container(
        width=SATELLITE_W, height=SATELLITE_H, background_color=s.TRANSPARENT
    )
    inner.add(icon, (SATELLITE_W - ICON_SIZE) // 2, 18)
    inner.add(caption, 0, 18 + ICON_SIZE + 8)

    button = Button(
        width=SATELLITE_W,
        height=SATELLITE_H,
        content_widget=inner,
        background_color=s.TRANSPARENT,
        corner_radius=s.ROW_RADIUS,
        outline_width=s.BORDER,
        outline_color=s.ACCENT,
        enable_click=on_click is not None,
        scale_by=0.0,
        **s.outline(),
    )
    if on_click is not None:
        button.on_clicked(on_click)
    return button


def _centre(task: Task) -> VerticalContainer:
    """The task itself, in the middle. Deliberately not pressable."""
    circle = VerticalContainer(
        width=CENTRE_SIZE,
        height=CENTRE_SIZE,
        corner_radius=CENTRE_SIZE // 2,
        border_width=s.BORDER,
        border_color=s.ACCENT,
        background_color=s.TRANSPARENT,
        inner_margin=(26, 48, 26, 0),
        spacing=2,
        **s.outline(),
    )
    inner_w = CENTRE_SIZE - 52
    circle.add(
        TextBox(
            task.title,
            font_size=17,
            font_weight=s.HEAVY,
            text_color=s.TEXT,
            alignment="center",
            width=inner_w,
        )
    )
    circle.add(
        TextBox(
            task.source,
            font_size=s.SMALL_SIZE,
            font_weight=s.MEDIUM,
            text_color=s.TEXT_DIM,
            alignment="center",
            width=inner_w,
            wrap_words=False,
        )
    )
    return circle


def build_action_menu(
    task: Task,
    *,
    audio_available: bool = False,
    on_primary: Callable[[], None],
    on_secondary: Callable[[], None],
    on_audio: Callable[[], None] | None = None,
    on_cancel: Callable[[], None],
) -> Container:
    """The four-direction menu for one task.

    Args:
        audio_available: False while the gateway cannot transcribe. The
            Audio position is then drawn but not pressable, rather than
            hidden, so the geometry the wearer has learned does not shift.
    """
    host = Container(width=WIDTH, height=HEIGHT, background_color=s.TRANSPARENT)

    cx = WIDTH // 2
    cy = HEIGHT // 2

    host.add(_centre(task), cx - CENTRE_SIZE // 2, cy - CENTRE_SIZE // 2)

    # Top: audio. Always in the same place, offered or not.
    host.add(
        _satellite("Audio", "audio.png", on_audio if audio_available else None),
        cx - SATELLITE_W // 2,
        0,
    )

    # Left and right: whatever the gateway is willing to accept. An empty
    # slot stays empty.
    if task.primary is not None:
        host.add(
            _satellite(task.primary.label, "check.png", on_primary),
            0,
            cy - SATELLITE_H // 2,
        )
    if task.secondary is not None:
        host.add(
            _satellite(task.secondary.label, "cross.png", on_secondary),
            WIDTH - SATELLITE_W,
            cy - SATELLITE_H // 2,
        )

    # Bottom: the way out. Always present.
    host.add(
        _satellite("Cancel", "cancel.png", on_cancel),
        cx - SATELLITE_W // 2,
        HEIGHT - SATELLITE_H,
    )

    return host


def labels_for(task: Task) -> tuple[str | None, str | None]:
    """What the two dynamic positions say, for tests and screenshots."""

    def name(action: Action | None) -> str | None:
        return None if action is None else action.label

    return name(task.primary), name(task.secondary)


__all__ = ["HEIGHT", "WIDTH", "build_action_menu", "labels_for"]

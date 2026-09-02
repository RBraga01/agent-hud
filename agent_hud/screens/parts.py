"""The pieces every screen is built from.

Cards, rows, labels and the two kinds of button. Keeping them here is what
makes the six screens look like one product: a change to how a row reads
happens once, not six times.

Everything that can be pressed is a framework ``Button``. That is not a
styling choice. RavenOS decides whether a wearer activates a control by
double-blinking at it or by holding a dwell, and it delivers either one as
that button's ``clicked`` signal. Building a "button" out of a plain
container would mean re-implementing activation ourselves from gaze
position, which is precisely what this product must never do.
"""

from __future__ import annotations

import os
from collections.abc import Callable

from raven_framework.components.button import Button
from raven_framework.components.horizontal_container import HorizontalContainer
from raven_framework.components.icon import Icon
from raven_framework.components.text_box import TextBox
from raven_framework.components.vertical_container import VerticalContainer

from . import style as s

_ASSETS = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets")

# Which mark stands for which source. The glasses choose it from the
# source name; the gateway never sends an image, so a hostile or broken
# gateway cannot put arbitrary graphics on the display.
# How the wearer activates things. One setting, applying to every button
# on every screen, so it is held here rather than threaded through ten
# builder signatures that would all pass the same pair of values.
#
# It never changes *whether* a control can be activated, only how long a
# dwell takes. There is no value it can hold that makes looking enough.
_activation = {"mode": "double_blink", "dwell_ms": 1500}


def set_activation(mode: str, dwell_ms: int) -> None:
    """Apply the wearer's choice to every button built from now on."""
    _activation["mode"] = mode
    _activation["dwell_ms"] = int(dwell_ms)


def _dwell() -> dict:
    return s.dwell_settings(_activation["mode"], _activation["dwell_ms"])


_SOURCE_MARKS = {
    "claude": "claude.png",
    "codex": "codex.png",
    "github": "github.png",
}


def source_icon(source: str, size: int = s.ROW_ICON_SIZE) -> Icon:
    """The little mark for a source. Unknown sources get a plain ring."""
    name = _SOURCE_MARKS.get(source.strip().lower(), "generic.png")
    return Icon(
        is_square=True,
        background_image_path=os.path.join(_ASSETS, "sources", name),
        size=size,
        enable_click=False,
    )


def card(width: int, *, spacing: int = s.CARD_SPACING) -> VerticalContainer:
    """The outlined panel every screen sits inside.

    Content-hugging: no fixed height, because a container sized exactly to
    its children clips them, and one sized larger leaves a lit void on a
    display where every drawn pixel is light the wearer has to look past.
    """
    return VerticalContainer(
        width=width,
        background_color=s.TRANSPARENT,
        border_width=s.BORDER,
        border_color=s.ACCENT,
        corner_radius=s.CARD_RADIUS,
        inner_margin=(s.CARD_MARGIN, s.CARD_MARGIN, s.CARD_MARGIN, s.CARD_MARGIN + 6),
        spacing=spacing,
        **s.outline(),
    )


def label(text: str, width: int | None = None) -> TextBox:
    """A small tracked upper-case label, in the accent colour."""
    return TextBox(
        s.label_text(text),
        font_size=s.LABEL_SIZE,
        font_weight=s.HEAVY,
        text_color=s.ACCENT,
        width=width,
        wrap_words=False,
    )


def title(text: str, width: int | None = None) -> TextBox:
    """The name of the thing on screen."""
    return TextBox(
        text,
        font_size=s.TITLE_SIZE,
        font_weight=s.HEAVY,
        text_color=s.TEXT,
        width=width,
    )


def body(text: str, width: int | None = None) -> TextBox:
    """Reading text. Medium weight so it survives daylight."""
    return TextBox(
        text,
        font_size=s.BODY_SIZE,
        font_weight=s.MEDIUM,
        text_color=s.TEXT,
        width=width,
    )


def small(text: str, width: int | None = None, *, align: str = "right") -> TextBox:
    """The quiet line, such as the count of what did not fit."""
    return TextBox(
        text,
        font_size=s.SMALL_SIZE,
        font_weight=s.MEDIUM,
        text_color=s.TEXT_DIM,
        alignment=align,
        width=width,
        wrap_words=False,
    )


def rule(width: int) -> VerticalContainer:
    """A hairline between the heading and the text under it."""
    return VerticalContainer(
        width=width,
        height=s.BORDER,
        background_color=s.ACCENT,
        corner_radius=0,
    )


def primary_button(
    text: str, on_click: Callable[[], None], *, width: int = s.BUTTON_MIN_WIDTH
) -> Button:
    """The action being suggested. Filled, so it is the brightest thing.

    Only ever one per screen. On a display that can only add light, a
    filled shape is the loudest thing available, and two of them would
    make the choice harder rather than clearer.

    ``use_fill_dwell`` is off here, and that is load-bearing: with it on,
    the framework throws away the background colour you passed and paints
    its own dwell fill instead, so the button silently comes out hollow.
    """
    button = Button(
        width=width,
        height=s.BUTTON_HEIGHT,
        center_text=text,
        background_color=s.ACCENT,
        text_color=s.TEXT,
        text_size=s.BODY_SIZE,
        font_weight=s.HEAVY,
        corner_radius=s.BUTTON_RADIUS,
        outline_width=0,
        scale_by=0.0,
        use_gradient_border=False,
        # The fill dwell would throw away the background colour that makes
        # this button the filled one, so the outline dwell is used here.
        use_fill_dwell=False,
        dwell_time=_dwell()["dwell_time"],
    )
    button.on_clicked(on_click)
    return button


def secondary_button(
    text: str, on_click: Callable[[], None], *, width: int = s.BUTTON_MIN_WIDTH
) -> Button:
    """The way out. Outline only, so it never competes with the primary."""
    button = Button(
        width=width,
        height=s.BUTTON_HEIGHT,
        center_text=text,
        background_color=s.TRANSPARENT,
        text_color=s.TEXT,
        text_size=s.BODY_SIZE,
        font_weight=s.MEDIUM,
        corner_radius=s.BUTTON_RADIUS,
        outline_width=s.BORDER,
        outline_color=s.ACCENT,
        scale_by=0.0,
        **_dwell(),
        **s.outline(),
    )
    button.on_clicked(on_click)
    return button


def row_button(
    source: str,
    summary: str,
    on_click: Callable[[], None] | None,
    *,
    width: int,
) -> Button:
    """One task in a list: its mark, its source, and one line about it."""
    text_width = width - s.ROW_ICON_SIZE - 56

    text = VerticalContainer(width=text_width, spacing=1)
    text.add(
        TextBox(
            source,
            font_size=s.ROW_TITLE_SIZE,
            font_weight=s.HEAVY,
            text_color=s.TEXT,
            width=text_width,
            wrap_words=False,
        )
    )
    if summary:
        text.add(
            TextBox(
                summary,
                font_size=s.BODY_SIZE,
                font_weight=s.MEDIUM,
                text_color=s.TEXT_DIM,
                width=text_width,
                wrap_words=False,
            )
        )

    # Button stretches its content to fill, and a container stacks from its
    # own top edge, so the inner margin is what keeps the first line off
    # the border and centres the pair within the row.
    inner = HorizontalContainer(
        width=width, inner_margin=(16, 10, 16, 10), spacing=14
    )
    inner.add(source_icon(source))
    inner.add(text)

    button = Button(
        width=width,
        height=s.ROW_HEIGHT,
        content_widget=inner,
        corner_radius=s.ROW_RADIUS,
        outline_width=s.BORDER,
        outline_color=s.ACCENT,
        background_color=s.TRANSPARENT,
        enable_click=on_click is not None,
        scale_by=0.0,
        **_dwell(),
        **s.outline(),
    )
    if on_click is not None:
        button.on_clicked(on_click)
    return button


def button_row(width: int, buttons: list[Button]) -> HorizontalContainer:
    """The footer of a screen: the way back, then the way on.

    The height is stated rather than left to the layout. A container with
    no height reserves none, so the card above it closes early and the
    buttons spill through its bottom edge.
    """
    strip = HorizontalContainer(width=width, height=s.BUTTON_HEIGHT, spacing=16)
    for button in buttons:
        strip.add(button)
    return strip

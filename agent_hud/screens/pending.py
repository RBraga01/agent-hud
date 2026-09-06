"""The resting marker when work has been set aside.

The ordinary resting dot says "I am here and there is nothing for you".
This says "I am here and there is something, whenever you want it" -- and
it has to say that without nagging, because the whole point of setting
work aside is not being nagged.

Three signals, not one
----------------------
Colour alone would not do. The amber marker already means "you are not
seeing everything", and a calm display and a broken one must never look
alike, so borrowing amber here would make deferred work look like a
fault. Red would say the same thing louder.

So this stays the resting blue and carries its meaning in shape and
movement instead: an hourglass, and a slow pulse. Someone who cannot
separate the two blues still sees a different shape moving.

Drawn, not typed
----------------
The hourglass is painted rather than set as a character. ⌛ renders on
Windows because Segoe has it, and the glasses are not Windows -- a glyph
that silently falls back to a blank box on the device is exactly the kind
of thing that only shows up when it is too late to notice.

Bright shape, dark cut
----------------------
The waveguide only adds light: black is transparent, white is brightest.
So the disc is solid and the hourglass is cut out of it, rather than a
thin hourglass drawn on nothing. At this size a stroke is scattered by
the optics until little is left, which is the same reason the resting dot
is solid. The cut-out reads as a dark hourglass floating in a lit disc,
and every lit pixel is working.
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import (
    Property,
    QEasingCurve,
    QPointF,
    QPropertyAnimation,
    Qt,
)
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPolygonF
from PySide6.QtWidgets import QWidget

from . import style as s

# Bigger than the resting dot, because it now has to carry a shape. Below
# roughly this size the waist of the hourglass closes up on the display
# and it reads as a plain dot again.
SIZE = 34

# How much of the disc the hourglass occupies.
GLASS_WIDTH = 0.44
GLASS_HEIGHT = 0.52
CAP = 0.13  # the flat bars top and bottom, as a fraction of the disc

# Slow on purpose. A quick pulse reads as an alarm, and this is the
# opposite of an alarm: it is a thing waiting patiently to be noticed.
PULSE_MS = 2600
PULSE_FLOOR = 0.45


def _hourglass(size: int) -> QPainterPath:
    """The hourglass, as a path centred in a box of `size`."""
    width = size * GLASS_WIDTH
    height = size * GLASS_HEIGHT
    left = (size - width) / 2
    right = left + width
    top = (size - height) / 2
    bottom = top + height
    cap = height * CAP
    middle = size / 2

    # Two bars joined by a bowtie. The bars are what stop it reading as a
    # pair of loose triangles at this size.
    path = QPainterPath()
    path.addPolygon(
        QPolygonF(
            [
                QPointF(left, top),
                QPointF(right, top),
                QPointF(right, top + cap),
                QPointF(middle, middle),
                QPointF(right, bottom - cap),
                QPointF(right, bottom),
                QPointF(left, bottom),
                QPointF(left, bottom - cap),
                QPointF(middle, middle),
                QPointF(left, top + cap),
            ]
        )
    )
    path.closeSubpath()
    return path


class PendingMarker(QWidget):
    """A lit disc with an hourglass cut out of it, pulsing slowly.

    Activating it returns to the attention screen. It is the only way
    back in once work has been set aside, so it is a target rather than
    an ornament -- and it is larger than the resting dot partly for that
    reason, since gaze lands within a couple of degrees of where it means
    to.
    """

    def __init__(
        self,
        *,
        size: int = SIZE,
        color: str = s.ACCENT,
        on_open: Callable[[], None] | None = None,
        animate: bool = True,
    ) -> None:
        super().__init__()
        self._size = size
        self._color = QColor(color)
        self._on_open = on_open
        self._glass = _hourglass(size)
        self._level = 1.0
        self._pulse: QPropertyAnimation | None = None

        self.setFixedSize(size, size)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        if on_open is not None:
            self.setCursor(Qt.CursorShape.PointingHandCursor)

        if animate:
            self._start_pulse()

    # The pulse rides on the paint colour rather than a
    # QGraphicsOpacityEffect, and that is not a style choice. A widget
    # holds exactly one graphics effect, and setting a second deletes the
    # first: the app fades each new screen in through an effect of its
    # own, so a pulse living on an effect would be silently thrown away
    # the moment the wearer arrived at this screen -- which is the only
    # moment it is ever seen. Owning a property leaves the effect free.
    def _get_level(self) -> float:
        return self._level

    def _set_level(self, value: float) -> None:
        self._level = float(value)
        self.update()

    level = Property(float, _get_level, _set_level)

    def _start_pulse(self) -> None:
        """Breathe the marker in and out.

        Alpha, not a colour ramp towards black: on this display less alpha
        is simply less light, and the hourglass stays as crisp at the
        bottom of the pulse as at the top.
        """
        pulse = QPropertyAnimation(self, b"level", self)
        pulse.setDuration(PULSE_MS)
        pulse.setStartValue(1.0)
        pulse.setKeyValueAt(0.5, PULSE_FLOOR)
        pulse.setEndValue(1.0)
        pulse.setEasingCurve(QEasingCurve.Type.InOutSine)
        pulse.setLoopCount(-1)
        pulse.start()
        self._pulse = pulse

    def stop(self) -> None:
        """Stop the pulse. Called before the marker is thrown away, so a
        loop does not keep running against a dead widget."""
        if self._pulse is not None:
            self._pulse.stop()
            self._pulse = None

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt's name
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        # The disc, then the hourglass taken back out of it. Even-odd
        # filling would leave the bowtie's crossing point lit.
        disc = QPainterPath()
        disc.addEllipse(0, 0, self._size, self._size)

        color = QColor(self._color)
        color.setAlphaF(max(0.0, min(1.0, self._level)))
        painter.fillPath(disc.subtracted(self._glass), color)
        painter.end()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 - Qt's name
        if self._on_open is not None and self.rect().contains(event.pos()):
            self._on_open()


__all__ = ["SIZE", "PendingMarker"]

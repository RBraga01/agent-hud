"""When the detail panel is showing.

Deliberately free of any framework code. On the glasses the gaze comes
from your eye; in the simulator it comes from the mouse. Neither matters
here — this only sees a point and whether it landed inside a rectangle,
which is what makes the behaviour testable at all.

Closing is not immediate. Eye tracking on this hardware is accurate to
two or three degrees, so a gaze that is "on" something still wanders.
Closing the instant it strays would make the panel flicker while you are
trying to read it.
"""

from __future__ import annotations

from dataclasses import dataclass

DEFAULT_GRACE_SECONDS = 2.0


@dataclass(frozen=True)
class Rect:
    """A region on the display, in pixels from the top left."""

    x: int
    y: int
    width: int
    height: int

    def contains(self, x: int, y: int) -> bool:
        """True when the point falls inside. A region with no area holds nothing."""
        if self.width <= 0 or self.height <= 0:
            return False
        return (
            self.x <= x < self.x + self.width
            and self.y <= y < self.y + self.height
        )


class DetailPanel:
    """Tracks whether the detail is showing, and decides when to hide it.

    Opened on demand, by staring at the count. Closes once the gaze has
    been away for the whole grace period. Looking back restarts the clock.
    """

    def __init__(self, grace_seconds: float = DEFAULT_GRACE_SECONDS) -> None:
        if grace_seconds <= 0:
            raise ValueError(
                f"grace_seconds must be greater than zero, got {grace_seconds!r}"
            )
        self._grace_seconds = grace_seconds
        self._is_open = False
        # When the gaze was last known to be on the panel. The grace period
        # is measured from here rather than from the first update that saw
        # the gaze elsewhere: gaze is only sampled every few seconds, so
        # measuring from the observation would add a whole poll interval of
        # lag before the panel closed.
        self._last_inside: float | None = None

    @property
    def is_open(self) -> bool:
        return self._is_open

    def open(self, now: float) -> None:
        """Show the panel.

        Opening counts as having just looked at it, so a panel that is
        opened and then ignored fades out after the grace period rather
        than lingering.
        """
        self._is_open = True
        self._last_inside = now

    def close(self) -> None:
        """Hide the panel now, without waiting."""
        self._is_open = False
        self._last_inside = None

    def update(self, *, gaze_inside: bool, now: float) -> bool:
        """Advance the clock. Returns whether the panel should be showing."""
        if not self._is_open:
            return False

        if gaze_inside:
            self._last_inside = now
            return True

        if (
            self._last_inside is not None
            and now - self._last_inside >= self._grace_seconds
        ):
            self.close()
            return False

        return True

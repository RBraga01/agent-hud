"""The screen.

Deliberately thin. Every decision worth testing lives in items.py,
client.py and interaction.py, which need no framework at all. What is
left here is placing widgets and moving values between them.

Layout follows Raven's guidance: content to the right, because the
display sits over the right eye; nothing smaller than body text; and
almost nothing on screen unless something is actually waiting on you.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Iterable

from raven_framework import RavenApp, Routine, TextBox, VerticalContainer
from raven_framework.components.icon import Icon
from raven_framework.helpers.async_runner import AsyncRunner

from .client import DEFAULT_TIMEOUT_SECONDS, FetchResult, fetch_items
from .config import Settings, load_settings
from .interaction import DEFAULT_GRACE_SECONDS, DetailPanel, Rect
from .items import Item, needs_you_count

# The app container the framework hands us, and where it sits on the display.
APP_SIZE = 640
APP_OFFSET_X = 40
APP_OFFSET_Y = 50

COUNT_ICON_SIZE = 120
COUNT_DWELL_MS = 1200
# Enough that nothing sits against the edge of vision, where it is both
# hard to read and easy to trigger by accident.
EDGE_MARGIN = 24

IDLE_DOT_SIZE = 14

# The panel is narrower than the container and pushed right. The display
# sits over the right eye, so the guidance is to assume asymmetry rather
# than centre things for visual balance.
PANEL_WIDTH = 520
PANEL_HEIGHT = 380
PANEL_X = APP_SIZE - PANEL_WIDTH - EDGE_MARGIN
PANEL_Y = 24

# Six lines maximum on screen. Each item costs two, leaving room for the
# overflow line.
MAX_PANEL_ITEMS = 2

GAZE_TICK_MS = 100

DIM_GRAY = "#3A3A3A"
WHITE = "#FFFFFF"


class AgentHud(RavenApp):
    """Shows how many things are waiting on you, and what they are.

    Args:
        parent: Qt parent.
        settings: Where the gateway is and how often to ask. Read from the
            environment when not given.
        fetch: How to reach the gateway. Replaced in tests.
        gaze: Where the wearer is looking, or None if unknown.
        clock: Source of the current time, in seconds.
        auto_start: Whether to start the timers. False in tests.
    """

    def __init__(
        self,
        parent=None,
        *,
        settings: Settings | None = None,
        fetch: Callable[..., FetchResult] | None = None,
        gaze: Callable[[], tuple[int, int] | None] | None = None,
        clock: Callable[[], float] | None = None,
        auto_start: bool = True,
    ) -> None:
        super().__init__(parent)

        self._settings = settings or load_settings()
        self._fetch = fetch or fetch_items
        self._gaze = gaze or _default_gaze
        self._clock = clock or time.monotonic

        self._items: list[Item] = []
        self._online = True
        self._count_text = ""
        self._panel = DetailPanel(grace_seconds=DEFAULT_GRACE_SECONDS)

        self._async = AsyncRunner()
        self._pending: FetchResult | None = None
        self._poll_routine: Routine | None = None
        self._gaze_routine: Routine | None = None

        self._build_widgets()
        self._render()

        if auto_start:
            self.refresh_now()
            self._start_timers()

    # -- construction ---------------------------------------------------

    def _build_widgets(self) -> None:
        self._count_icon = Icon(
            size=COUNT_ICON_SIZE,
            center_text="",
            text_size=45,
            text_color=WHITE,
            background_color="black",
            dwell_time=COUNT_DWELL_MS,
        )
        self._count_icon.on_clicked(self.open_panel)

        self._count_label = TextBox("need you", font_type="body", alignment="center")

        self._idle_dot = Icon(
            size=IDLE_DOT_SIZE,
            background_color=DIM_GRAY,
            outline_width=0,
            enable_click=False,
            disabled=True,
        )

        self._panel_box = VerticalContainer(
            width=PANEL_WIDTH, height=PANEL_HEIGHT, spacing=10
        )

    # -- what the tests read --------------------------------------------

    @property
    def count_text(self) -> str:
        """The number shown, as text. Empty when nothing is waiting."""
        return self._count_text

    @property
    def is_idle(self) -> bool:
        """True when nothing is waiting on you."""
        return needs_you_count(self._items) == 0

    @property
    def is_online(self) -> bool:
        """False when the last attempt to reach the gateway failed."""
        return self._online

    @property
    def is_panel_open(self) -> bool:
        return self._panel.is_open

    @property
    def panel_lines(self) -> list[tuple[str, str]]:
        """Title and detail for each item the panel is showing."""
        return [(item.title, item.detail) for item in self._waiting()[:MAX_PANEL_ITEMS]]

    def panel_region(self) -> Rect:
        """Where the panel sits on the display. Empty when closed."""
        if not self._panel.is_open:
            return Rect(x=0, y=0, width=0, height=0)
        return Rect(
            x=APP_OFFSET_X + PANEL_X,
            y=APP_OFFSET_Y + PANEL_Y,
            width=PANEL_WIDTH,
            height=PANEL_HEIGHT,
        )

    # -- behaviour ------------------------------------------------------

    def _waiting(self) -> list[Item]:
        return [item for item in self._items if item.needs_you]

    def open_panel(self) -> None:
        """Show the detail. Does nothing when there is nothing to show."""
        if self.is_idle:
            return
        self._panel.open(now=self._clock())
        self._render()

    def tick_gaze(
        self, gaze_position: tuple[int, int] | None = None, now: float | None = None
    ) -> None:
        """Advance the panel's close timer using where the wearer is looking.

        An unknown position is treated as no news rather than as looking
        away: losing tracking for a moment must not dismiss what you were
        part way through reading.
        """
        if not self._panel.is_open:
            return
        if gaze_position is None:
            return

        was_open = self._panel.is_open
        still_open = self._panel.update(
            gaze_inside=self.panel_region().contains(*gaze_position),
            now=self._clock() if now is None else now,
        )
        if was_open and not still_open:
            self._render()

    def apply(self, result: FetchResult) -> None:
        """Take a new result from the gateway and redraw.

        A failed fetch keeps the last known list on screen rather than
        blanking it, because an empty display and a broken one must not
        look the same.
        """
        self._online = result.ok
        if result.ok:
            self._items = result.items

        if self._panel.is_open and self.is_idle:
            self._panel.close()

        self._render()

    def refresh_now(self) -> None:
        """Fetch once, on this thread. Used at startup and in tests."""
        self.apply(
            self._fetch(self._settings.gateway_url, DEFAULT_TIMEOUT_SECONDS)
        )

    # -- drawing --------------------------------------------------------

    def _render(self) -> None:
        self.app.clear()

        if self._panel.is_open:
            self._render_panel()
            return

        if self.is_idle:
            self._count_text = ""
            self.app.add(
                self._idle_dot,
                APP_SIZE - IDLE_DOT_SIZE - EDGE_MARGIN,
                APP_SIZE // 2,
            )
            return

        self._count_text = str(needs_you_count(self._items))
        self._count_icon.set_text(self._count_text)
        icon_x = APP_SIZE - COUNT_ICON_SIZE - EDGE_MARGIN
        icon_y = APP_SIZE // 2 - COUNT_ICON_SIZE // 2
        self.app.add(self._count_icon, icon_x, icon_y)
        self.app.add(self._count_label, icon_x, icon_y + COUNT_ICON_SIZE + 6)

    def _render_panel(self) -> None:
        self._panel_box.clear()
        self._panel_box.add(*_panel_widgets(self._waiting()))
        self.app.add(self._panel_box, PANEL_X, PANEL_Y)

    # -- timers ---------------------------------------------------------

    def _start_timers(self) -> None:
        self._poll_routine = Routine(
            interval_ms=self._settings.poll_interval_ms,
            invoke=self._refresh_in_background,
            mode="repeat",
            parent=self,
        )
        self._gaze_routine = Routine(
            interval_ms=GAZE_TICK_MS,
            invoke=self._tick_gaze_from_sensor,
            mode="repeat",
            parent=self,
        )

    def _refresh_in_background(self) -> None:
        """Fetch off the main thread so the display never freezes."""

        def work() -> None:
            self._pending = self._fetch(
                self._settings.gateway_url, DEFAULT_TIMEOUT_SECONDS
            )

        # The completion callback takes no arguments and the worker's return
        # value is discarded — the framework's own documentation says
        # otherwise and following it raises. The result is carried on the
        # instance instead, which is what Raven's own example app does.
        self._async.run(work, on_complete=self._apply_pending)

    def _apply_pending(self) -> None:
        if self._pending is not None:
            self.apply(self._pending)
            self._pending = None

    def _tick_gaze_from_sensor(self) -> None:
        self.tick_gaze(gaze_position=self._gaze())


def _panel_widgets(items: Iterable[Item]) -> list:
    """Build the panel's text. Two lines per item, plus an overflow line."""
    items = list(items)
    widgets: list = []
    for item in items[:MAX_PANEL_ITEMS]:
        widgets.append(
            TextBox(item.title, font_type="headline", width=PANEL_WIDTH)
        )
        if item.detail:
            widgets.append(
                TextBox(item.detail, font_type="body", width=PANEL_WIDTH)
            )

    remaining = len(items) - MAX_PANEL_ITEMS
    if remaining > 0:
        widgets.append(
            TextBox(f"+{remaining} more", font_type="body", width=PANEL_WIDTH)
        )
    return widgets


def _default_gaze() -> tuple[int, int] | None:
    """Where the wearer is looking. The mouse cursor in the simulator."""
    from raven_framework.peripherals.eye_control import EyeControl

    global _eye_control
    if _eye_control is None:
        _eye_control = EyeControl()
    return _eye_control.get_gaze_position()


_eye_control = None

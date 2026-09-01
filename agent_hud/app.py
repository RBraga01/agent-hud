"""The screen.

Deliberately thin. Every decision worth testing lives in items.py,
client.py and interaction.py, which need no framework at all. What is
left here is placing widgets and moving values between them.

Layout follows Raven's guidance: content to the right, because the
display sits over the right eye; nothing smaller than body text; and
almost nothing on screen unless something is actually waiting on you.

Two framework behaviours shape this file:

* The container's clear() calls deleteLater() on every child, so a widget
  cannot be kept and re-added on the next redraw. Everything is built
  fresh each time.
* Because rebuilding resets the dwell ring, a redraw only happens when
  what is on screen would actually differ. Otherwise a poll every few
  seconds would wipe your progress every time you tried to stare at
  something.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from datetime import datetime

from raven_framework import (
    Button,
    Container,
    RavenApp,
    Routine,
    TextBox,
    VerticalContainer,
)
from raven_framework.components.icon import Icon
from raven_framework.helpers.async_runner import AsyncRunner
from raven_framework.helpers.themes import RAVEN_CORE as theme

from .client import DEFAULT_TIMEOUT_SECONDS, FetchResult, fetch_items
from .config import Settings, load_settings
from .interaction import DEFAULT_GRACE_SECONDS, DetailPanel, Rect
from .items import Item, needs_you_count

# The app container the framework hands us, and where it sits on the display.
APP_SIZE = 640
APP_OFFSET_X = 40
APP_OFFSET_Y = 50

# Enough that nothing sits against the edge of vision, where it is both
# hard to read and easy to trigger by accident.
EDGE_MARGIN = 24

# --- The outline language -------------------------------------------------
#
# Raven's own example apps get their legibility from bright white strokes,
# not from filled shapes: an outer frame around the app, and every row
# inside its own outlined pill. That is the right answer for this display.
# It only ever adds light, so it cannot darken a bright wall behind the
# text — but a thin, bright stroke reads against almost anything, and
# enclosing text gives the eye an edge to lock onto.
#
# The framework's Icon draws its ring only mid-dwell or when disabled, so
# a resting count has no outline of its own. The ring here is a bordered
# container placed behind it.
# Values come from the framework theme rather than being invented here, so
# the app sits inside Raven's own visual system: a white to Moon Silver
# diagonal gradient on every border, 3px wide, 20px corners. Overriding the
# border with flat white — which is what this did at first — switches that
# gradient off and makes the app look subtly foreign next to Raven's own.
WHITE = theme.basic_palette.white
STROKE_WIDTH = theme.borders.width
ROW_STROKE_WIDTH = 2
CORNER_RADIUS = theme.borders.corner_radius

FRAME_INSET = 6
FRAME_SIZE = APP_SIZE - FRAME_INSET * 2

COUNT_ICON_SIZE = 108
COUNT_RING_SIZE = 132
COUNT_TEXT_SIZE = 45
COUNT_DWELL_MS = 1200

# Margins follow ScrollableListCard, the closest example to this screen.
CARD_MARGIN_X = 25
CARD_MARGIN_TOP = 35
CARD_MARGIN_BOTTOM = 35
CARD_SPACING = 10

PANEL_TITLE = "Needs you"
CARD_WIDTH = FRAME_SIZE
ROW_WIDTH = CARD_WIDTH - CARD_MARGIN_X * 2
TITLE_HEIGHT = 46
OVERFLOW_LINE_HEIGHT = 34

# Cards are only as tall as what is in them. A full-height card around two
# rows leaves a large empty box hanging in the middle of your vision, which
# is exactly what Raven's compact card examples avoid.
COUNT_CARD_WIDTH = COUNT_RING_SIZE + CARD_MARGIN_X * 2 + 36
# Generous: a VerticalContainer lays out with a box layout, so if the card
# is only exactly tall enough the layout compresses the ring to fit the
# text's real height and the circle comes out clipped.
COUNT_LABEL_HEIGHT = 42
ROW_HEIGHT = 96
ROW_TEXT_INSET = 24
ROW_PAD_TOP = 14

IDLE_DOT_SIZE = 16
INCOMPLETE_DOT_SIZE = 20

# The panel sits inside the frame and is pushed right. The display covers
# the right eye, so the guidance is to assume asymmetry rather than centre
# things for visual balance.

# Six lines maximum on screen. Each row costs two, leaving room for the
# overflow line.
MAX_PANEL_ITEMS = 2

GAZE_TICK_MS = 100

# The clock sits above the frame and just left of the home button, which is
# where every Raven example puts it. It lives on the outer widget rather
# than the app container, so redrawing the app never disturbs it.
CLOCK_RIGHT_EDGE = 612
# Vertically centred on the home button, which the framework places with
# its circle spanning roughly y=15 to y=95.
CLOCK_Y = 42
CLOCK_WIDTH = 120
CLOCK_TICK_MS = 10_000

# Both markers take palette values from the theme. Yellow is Raven's own
# warning colour, and it is fully saturated, which is what this display
# needs — a dulled colour is one with less light in it.
IDLE_COLOR = theme.basic_palette.white
INCOMPLETE_COLOR = theme.basic_palette.yellow

# Checked against the simulator's waveguide blend in all three lighting
# presets. At night regular weight is fine, but in daylight the display
# only adds light and cannot darken what is behind it, so regular-weight
# body text washes out against a bright wall or window. Raven's own
# examples set titles heavy for the same reason.
TITLE_WEIGHT = "bold"
BODY_WEIGHT = "medium"


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
        self._dropped = 0
        self._fetching = False
        self._panel = DetailPanel(grace_seconds=DEFAULT_GRACE_SECONDS)

        self._async = AsyncRunner()
        self._pending: FetchResult | None = None
        self._poll_routine: Routine | None = None
        self._gaze_routine: Routine | None = None
        self._clock_routine: Routine | None = None
        self._rendered: tuple | None = None
        self._count_icon: Icon | None = None

        self._build_clock(running=auto_start)
        self._render()

        if auto_start:
            self.refresh_now()
            self._start_timers()

    # -- chrome ---------------------------------------------------------

    def _build_clock(self, *, running: bool) -> None:
        """The time, where Raven's own apps put it.

        Added to the outer widget, not the app container, so it survives
        every redraw and never has to be rebuilt.
        """
        self._clock_label = TextBox(
            _now_hhmm(),
            font_type="small",
            alignment="right",
            width=CLOCK_WIDTH,
            # Bold, because at 18px this is the least luminous thing on
            # screen and fades first in daylight. It is chrome, not
            # information, so fading is acceptable — but not by default.
            font_weight=TITLE_WEIGHT,
        )
        self.add(self._clock_label, CLOCK_RIGHT_EDGE - CLOCK_WIDTH, CLOCK_Y)
        if running:
            self._clock_routine = Routine(
                interval_ms=CLOCK_TICK_MS,
                invoke=self._update_clock,
                mode="repeat",
                parent=self,
            )

    def _update_clock(self) -> None:
        self._clock_label.set_text(_now_hhmm())

    # -- what the tests read --------------------------------------------

    @property
    def count_text(self) -> str:
        """The number shown, as text. Empty when nothing is waiting."""
        waiting = needs_you_count(self._items)
        return "" if waiting == 0 else str(waiting)

    @property
    def is_idle(self) -> bool:
        """True when nothing is waiting on you."""
        return needs_you_count(self._items) == 0

    @property
    def is_online(self) -> bool:
        """False when the last attempt to reach the gateway failed."""
        return self._online

    @property
    def is_complete(self) -> bool:
        """True when the list on screen can be trusted to be the whole list.

        False either because the gateway could not be reached or read, or
        because it answered with entries that had to be discarded. Both
        mean the same thing to the wearer: what you are looking at may be
        missing something.
        """
        return self._online and self._dropped == 0

    @property
    def is_fetching(self) -> bool:
        """True while a request is in flight."""
        return self._fetching

    @property
    def is_panel_open(self) -> bool:
        return self._panel.is_open

    @property
    def panel_lines(self) -> list[tuple[str, str]]:
        """Title and detail for each item the panel is showing."""
        return [(item.title, item.detail) for item in self._waiting()[:MAX_PANEL_ITEMS]]

    @property
    def overflow_count(self) -> int:
        """How many waiting items the panel had no room for."""
        return max(0, len(self._waiting()) - MAX_PANEL_ITEMS)

    def panel_region(self) -> Rect:
        """Where the panel sits on the display. Empty when closed.

        Computed from the same numbers that place the card, so the region the
        gaze is tested against is the region actually on screen.
        """
        if not self._panel.is_open:
            return Rect(x=0, y=0, width=0, height=0)
        height = self._panel_height()
        return Rect(
            x=APP_OFFSET_X + FRAME_INSET,
            y=APP_OFFSET_Y + (APP_SIZE - height) // 2,
            width=CARD_WIDTH,
            height=height,
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
        if not self._panel.is_open or gaze_position is None:
            return

        self._panel.update(
            gaze_inside=self.panel_region().contains(*gaze_position),
            now=self._clock() if now is None else now,
        )
        self._render()

    def apply(self, result: FetchResult) -> None:
        """Take a new result from the gateway and redraw.

        A failed fetch keeps the last known list on screen rather than
        blanking it, because an empty display and a broken one must not
        look the same.
        """
        self._online = result.ok
        self._dropped = result.dropped if result.ok else 0
        if result.ok:
            self._items = result.items

        if self._panel.is_open and self.is_idle:
            self._panel.close()

        self._render()

    def refresh_now(self) -> None:
        """Fetch once, on this thread. Used at startup and in tests."""
        self.apply(self._fetch(self._settings.gateway_url, DEFAULT_TIMEOUT_SECONDS))

    # -- drawing --------------------------------------------------------

    def _view(self) -> tuple:
        """Everything that affects what is drawn, so needless redraws are skipped."""
        if self._panel.is_open:
            return (
                "panel",
                tuple(self.panel_lines),
                self.overflow_count,
                self.is_complete,
            )
        if self.is_idle:
            return ("idle", self.is_complete)
        return ("count", self.count_text, self.is_complete)

    def _render(self) -> None:
        view = self._view()
        if view == self._rendered:
            return
        self._rendered = view

        # clear() deletes every child, so nothing built here may be reused
        # on a later pass. Each redraw builds new widgets.
        self.app.clear()
        self._count_icon = None

        if self.is_idle and self.is_complete:
            # Truly nothing to say. No frame, no chrome, just proof of life.
            self._draw_idle_dot()
            return

        # Two different layouts, so two different hosts. The panel is a
        # stacked card, exactly as the examples build one. The resting count
        # is placed by hand, which a VerticalContainer cannot do: its add()
        # only stacks and takes no coordinates.
        if self._panel.is_open:
            self._draw_panel()
        else:
            self._draw_count()

        if not self.is_complete:
            self._draw_incomplete_dot()

    def _card(self, width: int, height: int) -> VerticalContainer:
        """A card sized to its contents.

        This is the composition Raven's own examples use: a VerticalContainer
        with is_main_container set, which pulls the theme's background and
        gradient border, plus the margins ScrollableListCard uses.
        """
        card = VerticalContainer(
            width=width,
            height=height,
            is_main_container=True,
            inner_margin=(
                CARD_MARGIN_X,
                CARD_MARGIN_TOP,
                CARD_MARGIN_X,
                CARD_MARGIN_BOTTOM,
            ),
            spacing=CARD_SPACING,
        )
        return card

    def _panel_height(self) -> int:
        rows = len(self._waiting()[:MAX_PANEL_ITEMS])
        height = CARD_MARGIN_TOP + TITLE_HEIGHT + CARD_SPACING
        height += rows * (ROW_HEIGHT + CARD_SPACING)
        if self.overflow_count > 0:
            height += OVERFLOW_LINE_HEIGHT + CARD_SPACING
        return height + CARD_MARGIN_BOTTOM

    def _draw_count(self) -> None:
        """The resting count: a number in a ring, in a card of its own."""
        height = (
            CARD_MARGIN_TOP
            + COUNT_RING_SIZE
            + CARD_SPACING
            + COUNT_LABEL_HEIGHT
            + CARD_MARGIN_BOTTOM
        )
        card = self._card(COUNT_CARD_WIDTH, height)

        ring = Container(
            width=COUNT_RING_SIZE,
            height=COUNT_RING_SIZE,
            border_width=STROKE_WIDTH,
            corner_radius=COUNT_RING_SIZE // 2,
            background_color="transparent",
        )
        # The Icon carries the digit and the dwell arc; the ring around it is
        # the container, because a clickable Icon draws no outline of its own
        # until the dwell starts.
        self._count_icon = Icon(
            size=COUNT_ICON_SIZE,
            center_text=self.count_text,
            text_size=COUNT_TEXT_SIZE,
            text_color=WHITE,
            background_color="transparent",
            dwell_time=COUNT_DWELL_MS,
        )
        self._count_icon.on_clicked(self.open_panel)
        offset = (COUNT_RING_SIZE - COUNT_ICON_SIZE) // 2
        ring.add(self._count_icon, offset, offset)

        card.add(ring)
        card.add(
            TextBox(
                "need you",
                font_type="body",
                alignment="center",
                font_weight=BODY_WEIGHT,
                width=COUNT_RING_SIZE,
            )
        )

        # Right periphery, vertically centred: the display sits over the right
        # eye, so the guidance is to assume asymmetry.
        self.app.add(
            card,
            APP_SIZE - COUNT_CARD_WIDTH - EDGE_MARGIN,
            (APP_SIZE - height) // 2,
        )

    def _draw_panel(self) -> None:
        """A titled list, composed the way the Art Studio example composes one."""
        height = self._panel_height()
        frame = self._card(CARD_WIDTH, height)
        self.app.add(frame, FRAME_INSET, (APP_SIZE - height) // 2)
        frame.add(
            TextBox(
                PANEL_TITLE,
                font_size=theme.fonts.title.size,
                font_weight=TITLE_WEIGHT,
                width=ROW_WIDTH,
            )
        )
        for item in self._waiting()[:MAX_PANEL_ITEMS]:
            frame.add(_row(item))

        if self.overflow_count > 0:
            frame.add(
                TextBox(
                    f"+{self.overflow_count} more",
                    font_type="body",
                    font_weight=BODY_WEIGHT,
                    alignment="right",
                    width=ROW_WIDTH,
                )
            )

    def _draw_idle_dot(self) -> None:
        self.app.add(
            _dot(IDLE_DOT_SIZE, IDLE_COLOR),
            APP_SIZE - IDLE_DOT_SIZE - EDGE_MARGIN,
            APP_SIZE // 2,
        )

    def _draw_incomplete_dot(self) -> None:
        """A separate marker so a calm display and a broken one never look
        like the same thing.

        Shown when the gateway could not be reached, and also when it sent
        entries that had to be discarded: in both cases the list on screen
        may be missing something, which is the only thing this app must
        never get wrong.

        Placed on the app rather than inside the card, so it lands in the
        same spot whichever of the two layouts is showing.
        """
        self.app.add(
            _dot(INCOMPLETE_DOT_SIZE, INCOMPLETE_COLOR),
            APP_SIZE - INCOMPLETE_DOT_SIZE - FRAME_INSET - CARD_MARGIN_X,
            APP_SIZE - INCOMPLETE_DOT_SIZE - FRAME_INSET - CARD_MARGIN_BOTTOM,
        )

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
        """Fetch off the main thread so the display never freezes.

        One at a time. The poll interval is shorter than the request
        timeout, so without this guard a slow gateway leaves several
        requests in flight and an older answer can land after a newer one,
        walking the display backwards. Skipping a tick is harmless; the
        next one is only seconds away.
        """
        if self._fetching:
            return
        self._fetching = True

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
        """Runs on the main thread once the worker finishes, always."""
        try:
            if self._pending is not None:
                self.apply(self._pending)
                self._pending = None
        finally:
            # Cleared even if the fetch or the redraw failed, or the guard
            # would latch and polling would stop for good.
            self._fetching = False

    def _tick_gaze_from_sensor(self) -> None:
        self.tick_gaze(gaze_position=self._gaze())


def _now_hhmm() -> str:
    """Wall-clock time, 24 hour, as Raven's examples show it."""
    return datetime.now().strftime("%H:%M")


def _dot(size: int, color: str) -> Icon:
    """A small solid marker.

    Solid, not a ring — and the distinction is the whole lesson of this
    display. A *dark* fill is invisible because it adds no light. A *bright*
    fill is the most visible thing available, because it adds the most. Big
    shapes therefore want strokes, so they do not glow as solid blocks, but
    a marker this small needs its light concentrated: a thin ring at this
    size is scattered by the optics until nothing is left.
    """
    # enable_click=False gates the dwell. disabled=True must NOT be used: the
    # framework renders a disabled icon at reduced opacity, which on a display
    # that can only add light means the marker fades into whatever is behind
    # it. That single flag was why this dot was invisible outdoors at every
    # size and colour tried.
    return Icon(
        size=size,
        background_color=color,
        outline_width=0,
        enable_click=False,
    )


def _row(item: Item) -> Button:
    """One item as a Button, which is what the examples use for list rows.

    A Button rather than a plain outlined container: it carries the theme's
    outline, corner radius and dwell fill, so the row behaves and reads like
    every other Raven row rather than merely resembling one.

    No action icon, and clicking is off. The chevron in Raven's list screens
    promises that the row opens something; these rows are for reading, so
    showing one would promise something that is not there.
    """
    # Button stretches its content widget to fill itself, and a
    # VerticalContainer stacks from its own top edge — so without an inner
    # margin the first line lands on the border. The top margin centres the
    # two lines within the row.
    inner = VerticalContainer(
        width=ROW_WIDTH,
        inner_margin=(ROW_TEXT_INSET, ROW_PAD_TOP, ROW_TEXT_INSET, 0),
        spacing=2,
    )
    inner.add(
        TextBox(
            item.title,
            font_type="headline",
            font_weight=TITLE_WEIGHT,
            width=ROW_WIDTH - ROW_TEXT_INSET * 2,
        )
    )
    if item.detail:
        inner.add(
            TextBox(
                item.detail,
                font_type="body",
                font_weight=BODY_WEIGHT,
                width=ROW_WIDTH - ROW_TEXT_INSET * 2,
            )
        )

    return Button(
        width=ROW_WIDTH,
        height=ROW_HEIGHT,
        content_widget=inner,
        enable_click=False,
        # No rest-state shrink: that animation belongs to a button you can
        # press, and it makes the embedded text size unpredictable.
        scale_by=0.0,
    )


def _default_gaze() -> tuple[int, int] | None:
    """Where the wearer is looking. The mouse cursor in the simulator."""
    from raven_framework.peripherals.eye_control import EyeControl

    global _eye_control
    if _eye_control is None:
        _eye_control = EyeControl()
    return _eye_control.get_gaze_position()


_eye_control = None

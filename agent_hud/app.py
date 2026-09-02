"""The screen.

Deliberately thin. Every decision worth testing lives elsewhere and needs
no framework: what a task is in ``tasks.py``, which screen the wearer is
on in ``navigation.py``, what motion plays in ``transitions.py``, and how
each screen is drawn in ``screens/``. What is left here is placing
widgets, forwarding events, and asking the gateway for the list.

The one rule this file exists to keep is about input. Gaze position is
read only to know where the wearer is looking. It never activates
anything. Activation arrives as a framework ``Button``'s ``clicked``
signal, which RavenOS emits when the wearer double-blinks at the control
or holds a dwell on it. Which of those two it was is the wearer's setting
and the operating system's business, not this app's.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from datetime import datetime

from raven_framework import Routine
from raven_framework.components.icon import Icon
from raven_framework.components.text_box import TextBox
from raven_framework.core.raven_app import RavenApp
from raven_framework.helpers.async_runner import AsyncRunner
from raven_framework.helpers.themes import RAVEN_CORE as theme

from .client import DEFAULT_TIMEOUT_SECONDS, FetchResult, fetch_tasks
from .config import Settings, load_settings
from .feedback import (
    Feedback,
    SendOutcome,
    SendResult,
    new_request_id,
    send_feedback,
)
from .navigation import Event, Nav, Screen, advance, nav_for_tasks
from .screens import (
    SendState,
    build_action_menu,
    build_attention,
    build_confirmation,
    build_result,
    build_task_detail,
    build_task_list,
)
from .screens import style as s
from .tasks import Task, find_task, needs_you_count
from .transitions import (
    APP_SIZE,
    IDLE_DOT_SIZE,
    INCOMPLETE_DOT_SIZE,
    centre_of,
    duration_ms,
    idle_dot_position,
    is_springy,
    transition_for,
    travel,
)

# The app container sits centred inside the 720 display, and the resting
# markers are placed against the display rather than a card, so they land
# in the same spot whichever screen is showing.
GAZE_TICK_MS = 200

CLOCK_RIGHT_EDGE = 596
CLOCK_Y = 22
CLOCK_WIDTH = 120
CLOCK_TICK_MS = 10_000

# Both markers take palette values from the theme. Yellow is Raven's own
# warning colour, and it is fully saturated, which is what this display
# needs: a dulled colour is one with less light in it.
IDLE_COLOR = theme.basic_palette.blue
INCOMPLETE_COLOR = theme.basic_palette.yellow

# What each outcome is allowed to say on screen. Only ACCEPTED becomes
# "Sent", and even that means no more than "the gateway took it".
_SEND_STATES = {
    SendOutcome.ACCEPTED: SendState.SENT,
    SendOutcome.STALE: SendState.STALE,
    SendOutcome.REJECTED: SendState.REFUSED,
    SendOutcome.UNREACHABLE: SendState.FAILED,
}


class AgentHud(RavenApp):
    """Shows how many things are waiting on you, and lets you answer them.

    Args:
        parent: Qt parent.
        settings: Where the gateway is and how often to ask. Read from the
            environment when not given.
        fetch: How to reach the gateway. Replaced in tests.
        send: How to send an answer back. Replaced in tests.
        gaze: Where the wearer is looking, or None if unknown.
        clock: Source of the current time, in seconds.
        auto_start: Whether to kick the first background fetch and start
            the poll and gaze timers. False in tests, which drive the
            fetch by hand.
    """

    def __init__(
        self,
        parent=None,
        *,
        settings: Settings | None = None,
        fetch: Callable[..., FetchResult] | None = None,
        send: Callable[..., SendResult] | None = None,
        gaze: Callable[[], tuple[int, int] | None] | None = None,
        clock: Callable[[], float] | None = None,
        auto_start: bool = True,
    ) -> None:
        super().__init__(parent)

        self._settings = settings or load_settings()
        self._fetch = fetch or fetch_tasks
        self._send = send or send_feedback
        self._gaze = gaze or _default_gaze
        self._clock = clock or time.monotonic

        self._tasks: list[Task] = []
        self._nav = Nav()
        self._gaze_position: tuple[int, int] | None = None

        self._online = True
        self._dropped = 0
        self._truncated = 0
        self._fetching = False

        # The answer in flight, if any. Kept on the instance so a redraw
        # cannot lose the request id a retry needs.
        self._send_state = SendState.SENDING
        self._send_reason = ""
        self._outgoing: Feedback | None = None
        self._send_result: SendResult | None = None
        self._sending = False

        self._async = AsyncRunner()
        self._pending: FetchResult | None = None
        self._poll_routine: Routine | None = None
        self._gaze_routine: Routine | None = None
        self._clock_routine: Routine | None = None
        self._rendered: tuple | None = None

        self._animate = self._settings.animations
        self._transitioning = False
        self._anim_group = None  # kept alive while a transition runs
        # The launch render, and the first data render right after it, are
        # instant. Motion starts once the app is actually on screen.
        self._first_data_render_done = False

        self._build_clock(running=auto_start)
        self._render()

        if auto_start:
            # The first fetch goes through the same background path the
            # poll timer uses, not a blocking call. Against a remote
            # gateway a slow or unreachable one would otherwise hold the
            # glasses on the resting frame for the whole request timeout
            # before the app appeared to start.
            self._refresh_in_background()
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
            # Bold, because at this size it is the least luminous thing on
            # screen and fades first in daylight. It is chrome, not
            # information, so fading is acceptable — but not by default.
            font_weight=s.HEAVY,
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
    def tasks(self) -> list[Task]:
        """Everything the gateway last reported."""
        return list(self._tasks)

    @property
    def waiting(self) -> list[Task]:
        """Only the tasks that need the wearer. This is what the list shows."""
        return [task for task in self._tasks if task.needs_you]

    @property
    def count_text(self) -> str:
        """The number shown, as text. Empty when nothing is waiting."""
        count = needs_you_count(self._tasks)
        return "" if count == 0 else str(count)

    @property
    def is_idle(self) -> bool:
        """True when nothing is waiting on you."""
        return needs_you_count(self._tasks) == 0

    @property
    def is_online(self) -> bool:
        """False when the last attempt to reach the gateway failed."""
        return self._online

    @property
    def is_complete(self) -> bool:
        """True when the list on screen can be trusted to be the whole list.

        False because the gateway could not be reached or read, because it
        answered with entries that had to be discarded, or because an
        entry's text had to be cut to fit. All mean the same thing to the
        wearer: what you are looking at may be missing something.
        """
        return self._online and self._dropped == 0 and self._truncated == 0

    @property
    def is_fetching(self) -> bool:
        """True while a request is in flight."""
        return self._fetching

    @property
    def screen(self) -> Screen:
        """Which of the six screens is showing."""
        return self._nav.screen

    @property
    def nav(self) -> Nav:
        """The whole navigation state. Device-local; never sent anywhere."""
        return self._nav

    @property
    def current_task(self) -> Task | None:
        """The task the wearer has open, if any."""
        return find_task(self._tasks, self._nav.task_id)

    @property
    def send_state(self) -> SendState:
        """How far the answer in flight has got, if there is one."""
        return self._send_state

    @property
    def gaze_position(self) -> tuple[int, int] | None:
        """Where the wearer is last known to have been looking.

        Read for focus only. Nothing in this app turns a gaze position
        into an action.
        """
        return self._gaze_position

    # -- events ---------------------------------------------------------

    def _fire(self, event: Event, **kwargs) -> None:
        """Hand an event to the state machine and redraw if it moved us."""
        moved = advance(self._nav, event, self._tasks, **kwargs)
        if moved == self._nav:
            return
        self._nav = moved
        self._render()

    def open_list(self) -> None:
        """From the count card into the list of what is waiting."""
        self._fire(Event.ACTIVATE)

    def select_task(self, task_id: str) -> None:
        """Open one task from the list."""
        self._fire(Event.ACTIVATE, task_id=task_id)

    def take_action(self) -> None:
        """Open the action menu for the task being read."""
        self._fire(Event.TAKE_ACTION)

    def select_primary(self) -> None:
        """Choose the primary action. This does not send it."""
        self._fire(Event.SELECT_PRIMARY)

    def select_secondary(self) -> None:
        """Choose the secondary action. This does not send it."""
        self._fire(Event.SELECT_SECONDARY)

    def confirm(self) -> None:
        """The only step that transmits. Everything before this was local.

        Moves to the result screen straight away, showing "Sending", and
        does the sending off the main thread. Freezing the display for a
        five second timeout would be its own kind of failure.
        """
        task = self.current_task
        if task is None or self._nav.action_id is None:
            return

        self._outgoing = Feedback(
            task_id=task.id,
            revision=task.revision,
            action_id=self._nav.action_id,
            request_id=new_request_id(),
        )
        self._send_state = SendState.SENDING
        self._send_reason = ""
        self._fire(Event.CONFIRM)
        self._send_in_background()

    def retry_send(self) -> None:
        """Send the same answer again, with the same request id.

        Offered only when we do not know whether the first attempt
        arrived. Reusing the id is what makes it safe: a gateway that did
        receive it recognises the second attempt rather than acting twice.
        """
        if self._outgoing is None or self._send_state is not SendState.FAILED:
            return
        self._send_state = SendState.SENDING
        self._send_reason = ""
        self._render()
        self._send_in_background()

    def read_again(self) -> None:
        """Go back to the task after it changed under a pending answer."""
        if self._nav.task_id is None:
            return
        task_id = self._nav.task_id
        self._outgoing = None
        self._fire(Event.BACK)
        self._fire(Event.ACTIVATE, task_id=task_id)

    def cancel(self) -> None:
        """Step back out of the current screen without doing anything."""
        self._fire(Event.CANCEL)

    def back(self) -> None:
        """Step back up one screen."""
        self._fire(Event.BACK)

    def scroll_up(self) -> None:
        self._fire(Event.SCROLL_UP)

    def scroll_down(self) -> None:
        self._fire(Event.SCROLL_DOWN)

    def tick_gaze(
        self, gaze_position: tuple[int, int] | None = None, now: float | None = None
    ) -> None:
        """Record where the wearer is looking. Deliberately does nothing else.

        Focus is the framework's job: a button under the gaze scales and
        lights on its own. This app never converts a gaze position into an
        activation, which is why there is no timer here and no state to
        advance.
        """
        self._gaze_position = gaze_position

    # -- data -----------------------------------------------------------

    def apply(self, result: FetchResult) -> None:
        """Take a new result from the gateway and redraw.

        A failed fetch keeps the last known list on screen rather than
        blanking it, because an empty display and a broken one must not
        look the same.
        """
        self._online = result.ok
        self._dropped = result.dropped if result.ok else 0
        self._truncated = result.truncated if result.ok else 0
        if result.ok:
            self._tasks = result.tasks

        # The only place a refresh may touch navigation, and it can only
        # ever move the wearer to a shallower screen.
        self._nav = nav_for_tasks(self._nav, self._tasks)

        self._render()
        # From here on, state changes animate. The launch render and this
        # first data render are instant — motion starts once the app is up.
        self._first_data_render_done = True

    def refresh_now(self) -> None:
        """Fetch once, on this thread, and apply the result.

        Startup goes through ``_refresh_in_background`` instead, so a slow
        gateway cannot hold the first frame. This blocking form is for
        tests, where a synchronous fetch against a local stub is what the
        assertions expect.
        """
        self.apply(self._fetch(self._settings.gateway_url, DEFAULT_TIMEOUT_SECONDS))

    # -- drawing --------------------------------------------------------

    def _view(self) -> tuple:
        """Everything that affects what is drawn, so needless redraws are skipped."""
        task = self.current_task
        return (
            self._nav.screen.value,
            self._nav.task_id,
            self._nav.action_id,
            self._nav.page,
            self._nav.stale,
            self.count_text,
            self.is_complete,
            self._send_state.value,
            self._send_reason,
            None if task is None else (task.revision, task.title, task.summary),
            tuple((t.id, t.source, t.summary) for t in self.waiting),
        )

    def _render(self) -> None:
        # A transition is playing; it will settle to the current state when
        # it finishes, so leave it alone.
        if self._transitioning:
            return

        view = self._view()
        if view == self._rendered:
            return

        animate = self._animate and self._first_data_render_done
        previous = None if self._rendered is None else self._rendered[0]
        move = transition_for(previous, view[0], animate=animate)
        self._rendered = view

        # clear() deletes every child, so nothing built here may be reused
        # on a later pass. Each redraw builds new widgets.
        self.app.clear()
        top = self._draw_current()

        if move != "none" and top is not None:
            self._animate_in(top, move)

    def _draw_current(self):
        """Build the widgets for the current screen. Returns the top widget."""
        screen = self._nav.screen

        if screen is Screen.IDLE and self.is_complete:
            # Truly nothing to say. No frame, no chrome, just proof of life.
            return self._draw_idle_dot()

        top = None
        if screen is Screen.IDLE:
            top = self._draw_idle_dot()
        elif screen is Screen.ATTENTION:
            top = self._place(
                build_attention(
                    needs_you_count(self._tasks), on_open=self.open_list
                )
            )
        elif screen is Screen.TASK_LIST:
            top = self._place(
                build_task_list(
                    self.waiting, page=self._nav.page, on_select=self.select_task
                )
            )
        elif screen is Screen.TASK_DETAIL:
            top = self._draw_task_detail()
        elif screen is Screen.ACTION_MENU:
            top = self._draw_action_menu()
        elif screen is Screen.CONFIRMATION:
            top = self._draw_confirmation()
        elif screen is Screen.RESULT:
            top = self._draw_result()

        if not self.is_complete:
            self._draw_incomplete_dot()
        return top

    def _draw_task_detail(self):
        task = self.current_task
        if task is None:
            return None
        return self._place(
            build_task_detail(
                task,
                page=self._nav.page,
                stale=self._nav.stale,
                on_back=self.back,
                on_take_action=self.take_action if task.has_actions else None,
                on_scroll_up=self.scroll_up,
                on_scroll_down=self.scroll_down,
            )
        )

    def _draw_action_menu(self):
        task = self.current_task
        if task is None:
            return None
        return self._place(
            build_action_menu(
                task,
                # Audio needs the gateway to transcribe, which is not built
                # yet. The position is drawn but not pressable, so the
                # geometry the wearer has learned does not shift later.
                audio_available=False,
                on_primary=self.select_primary,
                on_secondary=self.select_secondary,
                on_cancel=self.cancel,
            )
        )

    def _draw_confirmation(self):
        task = self.current_task
        if task is None:
            return None
        action = None
        for candidate in (task.primary, task.secondary):
            if candidate is not None and candidate.id == self._nav.action_id:
                action = candidate
        if action is None:
            return None
        return self._place(
            build_confirmation(
                task, action, on_cancel=self.cancel, on_ok=self.confirm
            )
        )

    def _draw_result(self):
        """What happened after OK. Says only what the gateway confirmed."""
        return self._place(
            build_result(
                self._send_state,
                task=self.current_task,
                reason=self._send_reason,
                on_back=self.back,
                on_retry=self.retry_send,
                on_read_again=self.read_again,
            )
        )

    def _place(self, widget):
        """Put a screen in the middle of the display."""
        x, y = centre_of(widget.width(), widget.height())
        self.app.add(widget, x, y)
        return widget

    def _draw_idle_dot(self):
        dot = _dot(IDLE_DOT_SIZE, IDLE_COLOR)
        x, y = idle_dot_position()
        self.app.add(dot, x, y)
        return dot

    def _draw_incomplete_dot(self) -> None:
        """A separate marker so a calm display and a broken one never look
        like the same thing.

        Shown when the gateway could not be reached, and also when it sent
        entries that had to be discarded or text that had to be cut: in
        every case the list on screen may be missing something, which is
        the only thing this app must never get wrong.

        Placed against the display rather than inside a card, so it lands
        in the same spot on every screen.
        """
        self.app.add(
            _dot(INCOMPLETE_DOT_SIZE, INCOMPLETE_COLOR),
            APP_SIZE - INCOMPLETE_DOT_SIZE - 40,
            APP_SIZE - INCOMPLETE_DOT_SIZE - 40,
        )

    # -- transitions ----------------------------------------------------

    def _animate_in(self, widget, move: str) -> None:
        """Slide-and-fade the newly built screen into place.

        A geometry animation would fight the framework's fixed widget
        sizes, so the motion is a short vertical travel plus an opacity
        ramp — enough to read as moving into a task rather than a pop.
        """
        from PySide6.QtCore import QParallelAnimationGroup, QPoint
        from PySide6.QtWidgets import QGraphicsOpacityEffect
        from raven_framework import RavenCurve, make_property_animation

        home = widget.pos()
        widget.move(QPoint(home.x(), home.y() + travel(move)))

        effect = QGraphicsOpacityEffect(widget)
        effect.setOpacity(0.0)
        widget.setGraphicsEffect(effect)

        curve = RavenCurve.OUT_BACK if is_springy(move) else RavenCurve.OUT_CUBIC
        dur = duration_ms(move)

        group = QParallelAnimationGroup(self)
        group.addAnimation(
            make_property_animation(widget, b"pos", widget.pos(), home, dur, curve)
        )
        group.addAnimation(
            make_property_animation(
                effect, b"opacity", 0.0, 1.0, dur, RavenCurve.OUT_CUBIC
            )
        )
        self._transitioning = True
        self._anim_group = group
        group.finished.connect(self._settle)
        group.start()

    def _settle(self) -> None:
        """After a transition: drop to a clean rebuild of the final state."""
        self._transitioning = False
        self._anim_group = None
        self._rendered = None
        self._render()

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

    def _send_in_background(self) -> None:
        """Send the pending answer off the main thread. One at a time."""
        if self._sending or self._outgoing is None:
            return
        self._sending = True
        outgoing = self._outgoing

        def work() -> None:
            self._send_result = self._send(
                self._settings.gateway_base, outgoing, DEFAULT_TIMEOUT_SECONDS
            )

        self._async.run(work, on_complete=self._apply_send_result)

    def _apply_send_result(self) -> None:
        """Runs on the main thread once the send finishes, always."""
        try:
            result = self._send_result
            self._send_result = None
            if result is None:
                # The worker never produced one, so we genuinely do not
                # know whether it arrived. That is what FAILED means.
                self._send_state = SendState.FAILED
                self._send_reason = ""
            else:
                self._send_state = _SEND_STATES[result.outcome]
                self._send_reason = result.reason
        finally:
            self._sending = False
            self._render()

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
    # enable_click=False gates the dwell. disabled=True must NOT be used:
    # the framework dims a disabled icon, and dim is the one thing a marker
    # this small cannot afford.
    return Icon(
        is_square=False,
        size=size,
        background_color=color,
        enable_click=False,
    )


def _default_gaze() -> tuple[int, int] | None:
    """Where the wearer is looking. The mouse cursor in the simulator."""
    from raven_framework.peripherals.eye_control import EyeControl

    try:
        return EyeControl().get_gaze_position()
    except Exception:
        # Losing the sensor must not take the display down. Unknown is a
        # perfectly good answer here, because nothing depends on it.
        return None

"""Which screen the wearer is on, and what moves them between screens.

Framework-free on purpose. Every rule about where a button leads lives
here, as a plain function over plain data, so it can be checked
exhaustively without a display attached. ``app.py`` only draws whatever
screen this reports and hands back the events it collects.

Two rules shape the whole module:

* **Selecting an action never sends it.** Choosing "Approve" opens the
  confirmation screen and nothing else. Only the app, and only after
  ``CONFIRM``, talks to the gateway.
* **The gateway never steers the wearer.** A refresh may pull someone
  *out* of a screen that has stopped making sense — the task vanished, or
  it changed underneath a pending confirmation — but it may never push
  them somewhere they did not ask to go.

The events are deliberately abstract. ``ACTIVATE`` does not say whether
the wearer double-blinked or held a dwell; RavenOS decides that and the
app never needs to know. What it does say is that gaze *position* is not
in this list at all: looking at something changes focus, and focus alone
never advances the machine.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from enum import Enum

from .tasks import Task, find_task, needs_you_count

# How much of a task's detail fits on one page. Paging rather than
# smooth scrolling is deliberate: it is one glance per page instead of
# sustained attention on moving text, which is tiring on a headset.
DETAIL_PAGE_CHARS = 360


class Screen(str, Enum):
    """The screens, from resting to deepest."""

    IDLE = "idle"
    ATTENTION = "attention"
    TASK_LIST = "task_list"
    TASK_DETAIL = "task_detail"
    ACTION_MENU = "action_menu"
    CONFIRMATION = "confirmation"
    LISTENING = "listening"
    PROCESSING = "processing"
    REVIEW = "review"
    RESULT = "result"
    UNAVAILABLE = "unavailable"


class Event(str, Enum):
    """What the wearer did, with the input method already resolved away."""

    ACTIVATE = "activate"
    BACK = "back"
    CANCEL = "cancel"
    TAKE_ACTION = "take_action"
    SELECT_PRIMARY = "select_primary"
    SELECT_SECONDARY = "select_secondary"
    SELECT_AUDIO = "select_audio"
    CONFIRM = "confirm"
    RETRY = "retry"
    SCROLL_UP = "scroll_up"
    SCROLL_DOWN = "scroll_down"


@dataclass(frozen=True)
class Nav:
    """Where the wearer is. Device-local, never shared with the gateway.

    Attributes:
        screen: The screen being drawn.
        task_id: Which task is open, on the screens that show one.
        action_id: Which action is being confirmed, on CONFIRMATION.
        page: Which page of a long detail is showing.
        revision: The revision of the task when it was opened. Compared
            against a refresh so a confirmation cannot outlive its task.
        stale: True when a refresh pulled the wearer back because the task
            changed. The screen says so; the next move clears it.
    """

    screen: Screen = Screen.IDLE
    task_id: str | None = None
    action_id: str | None = None
    page: int = 0
    revision: int | None = None
    stale: bool = False


# How many polls in a row must fail before the display stops showing the
# last known list and says the gateway is gone. A couple of missed polls
# is a wobbly network; a dozen is a gateway that is not there, and
# presenting stale work as current for ever would be its own kind of lie.
OFFLINE_PATIENCE = 8


def nav_for_connection(
    nav: Nav, *, failures: int, patience: int = OFFLINE_PATIENCE
) -> Nav:
    """Move to, or away from, the unavailable screen.

    Kept apart from ``nav_for_tasks`` because it answers a different
    question: not "is what I am showing still true" but "is anybody
    there". A wearer part way through answering something is left alone —
    the unavailable screen only takes over from the resting screens,
    where nothing is being lost by replacing them.
    """
    if failures >= patience:
        if nav.screen in (Screen.IDLE, Screen.ATTENTION, Screen.TASK_LIST):
            return replace(nav, screen=Screen.UNAVAILABLE, stale=False)
        return nav

    if nav.screen is Screen.UNAVAILABLE:
        # It answered. Go back to whatever the tasks say we should show;
        # nav_for_tasks sorts out which that is.
        return replace(nav, screen=Screen.IDLE, stale=False)

    return nav


def page_count(task: Task | None) -> int:
    """How many pages this task's detail needs. Always at least one."""
    if task is None or not task.detail:
        return 1
    return max(1, math.ceil(len(task.detail) / DETAIL_PAGE_CHARS))


def detail_page(task: Task | None, page: int) -> str:
    """The text for one page of a task's detail."""
    if task is None or not task.detail:
        return ""
    start = page * DETAIL_PAGE_CHARS
    return task.detail[start : start + DETAIL_PAGE_CHARS]


# Where the lower part of a card begins, as a fraction of its height.
# Looking below this line is what auto-scroll watches for.
SCROLL_ZONE_FROM = 0.70

# How long the gaze has to rest there before a page turns, per speed.
# Slower than a glance on purpose: passing your eyes across the bottom of
# a card while reading it must not turn the page under you.
SCROLL_DELAYS = {"slow": 2.4, "normal": 1.6, "fast": 1.0}


class AutoScroll:
    """Turning the page by looking at the bottom of it.

    The one place in this app where the gaze drives anything, and it is
    allowed for a specific reason: scrolling executes nothing. Nothing
    leaves the glasses, no agent is told anything, and the worst a
    mistake can do is show the next page of something you were reading.
    Every rule about gaze never *activating* still holds, because turning
    a page is not an activation.

    Off unless the wearer asks for it. It exists for people who find
    pressing a button for every page tiring, which is a real thing on a
    headset, and it is a preference rather than a default because for
    everyone else it would be a page turning by itself.
    """

    def __init__(self, *, enabled: bool = False, speed: str = "normal") -> None:
        self.enabled = enabled
        self.delay = SCROLL_DELAYS.get(speed, SCROLL_DELAYS["normal"])
        self._resting_since: float | None = None

    def reset(self) -> None:
        """Forget where the gaze was. Called whenever the screen changes."""
        self._resting_since = None

    def should_advance(
        self, *, inside_zone: bool, now: float
    ) -> bool:
        """Whether enough uninterrupted looking has happened to turn a page.

        Returns True once per rest. Looking away, or an unknown gaze
        position, starts the wait over rather than continuing it — losing
        tracking for a moment must not add up to a page turn.
        """
        if not self.enabled or not inside_zone:
            self._resting_since = None
            return False

        if self._resting_since is None:
            self._resting_since = now
            return False

        if now - self._resting_since >= self.delay:
            self._resting_since = None
            return True
        return False


def _open_task(nav: Nav, task: Task) -> Nav:
    return replace(
        nav,
        screen=Screen.TASK_DETAIL,
        task_id=task.id,
        action_id=None,
        page=0,
        revision=task.revision,
        stale=False,
    )


def _to_list(nav: Nav) -> Nav:
    return replace(
        nav, screen=Screen.TASK_LIST, action_id=None, page=0, stale=False
    )


def _select(nav: Nav, action) -> Nav:
    """Open confirmation for an action. This does not send anything."""
    if action is None:
        return nav
    return replace(
        nav, screen=Screen.CONFIRMATION, action_id=action.id, stale=False
    )


def advance(
    nav: Nav,
    event: Event,
    tasks: list[Task],
    *,
    task_id: str | None = None,
) -> Nav:
    """Where ``event`` leads from ``nav``. Pure; sends nothing.

    Args:
        nav: Where the wearer is now.
        event: What they did.
        tasks: The current list, for looking up what an id refers to.
        task_id: Which task, when the event is choosing one from the list.

    Returns:
        The new state, or ``nav`` unchanged when the event means nothing
        on this screen.
    """
    screen = nav.screen
    task = find_task(tasks, nav.task_id)

    if screen is Screen.ATTENTION and event is Event.ACTIVATE:
        return replace(nav, screen=Screen.TASK_LIST, stale=False)

    if screen is Screen.TASK_LIST:
        if event is Event.ACTIVATE:
            chosen = find_task(tasks, task_id)
            return nav if chosen is None else _open_task(nav, chosen)
        if event is Event.BACK:
            return replace(nav, screen=Screen.ATTENTION, task_id=None, stale=False)

    if screen is Screen.TASK_DETAIL:
        if event is Event.BACK:
            return _to_list(nav)
        if event is Event.TAKE_ACTION:
            if task is None or not task.has_actions:
                return nav
            return replace(nav, screen=Screen.ACTION_MENU, stale=False)
        if event is Event.SCROLL_DOWN:
            last = page_count(task) - 1
            return replace(nav, page=min(nav.page + 1, last), stale=False)
        if event is Event.SCROLL_UP:
            return replace(nav, page=max(nav.page - 1, 0), stale=False)

    if screen is Screen.ACTION_MENU:
        if event in (Event.CANCEL, Event.BACK):
            return replace(nav, screen=Screen.TASK_DETAIL, stale=False)
        if event is Event.SELECT_AUDIO:
            # Recording starts here. Nothing is sent by starting it, and
            # nothing is sent by stopping it either: the words come back
            # to be read first.
            return replace(nav, screen=Screen.LISTENING, stale=False)
        if event is Event.SELECT_PRIMARY and task is not None:
            return _select(nav, task.primary)
        if event is Event.SELECT_SECONDARY and task is not None:
            return _select(nav, task.secondary)

    if screen is Screen.LISTENING:
        if event in (Event.CANCEL, Event.BACK):
            return replace(nav, screen=Screen.ACTION_MENU, stale=False)
        if event is Event.CONFIRM:
            # Done speaking. The gateway has the recording now.
            return replace(nav, screen=Screen.PROCESSING, stale=False)

    if screen is Screen.PROCESSING and event in (Event.CANCEL, Event.BACK):
        return replace(nav, screen=Screen.ACTION_MENU, stale=False)

    if screen is Screen.REVIEW:
        if event in (Event.CANCEL, Event.BACK):
            # Wrong words. Say it again rather than trying to fix them by
            # eye -- editing text with a gaze is nobody's idea of a good
            # time, and the phone is there for when it matters.
            return replace(nav, screen=Screen.LISTENING, stale=False)
        if event is Event.CONFIRM:
            return replace(nav, screen=Screen.RESULT, stale=False)

    if screen is Screen.CONFIRMATION:
        if event in (Event.CANCEL, Event.BACK):
            return replace(
                nav, screen=Screen.ACTION_MENU, action_id=None, stale=False
            )
        if event is Event.CONFIRM:
            # The machine only records that the wearer confirmed. Actually
            # talking to the gateway is the app's job, and the result
            # screen must not claim success until it hears back.
            return replace(nav, screen=Screen.RESULT, stale=False)

    if screen is Screen.RESULT and event in (Event.BACK, Event.ACTIVATE):
        return _to_list(nav)

    if screen is Screen.UNAVAILABLE and event is Event.ACTIVATE:
        # Retrying is the app's job; the screen stays put until an answer
        # actually arrives, so nothing here pretends it has.
        return nav

    return nav


def nav_for_tasks(nav: Nav, tasks: list[Task]) -> Nav:
    """Reconcile where the wearer is against a freshly fetched list.

    This is the only place the gateway may influence navigation, and it
    can only ever move someone to a *shallower* screen. Nobody gets pulled
    deeper, or sideways into a task they did not open, because the list
    changed while they were reading.
    """
    waiting = needs_you_count(tasks)

    if nav.screen is Screen.IDLE:
        return replace(nav, screen=Screen.ATTENTION) if waiting else nav

    # Screens the gateway is not allowed to take away, whatever the list
    # says -- and this has to come before the "nothing is waiting" check
    # below, because answering something is exactly what empties the list.
    #
    # RESULT is the acknowledgement of something the wearer just did.
    # LISTENING, PROCESSING and REVIEW are somebody mid-sentence. A
    # refresh arriving in the middle of either would be the gateway
    # interrupting a person, which is the thing this function exists to
    # prevent.
    if nav.screen in (
        Screen.RESULT,
        Screen.LISTENING,
        Screen.PROCESSING,
        Screen.REVIEW,
    ):
        return nav

    if not waiting:
        # Everything resolved while they were looking at it. Back to rest.
        return Nav(screen=Screen.IDLE)

    if nav.screen in (Screen.ATTENTION, Screen.TASK_LIST):
        return nav

    task = find_task(tasks, nav.task_id)
    if task is None:
        # The task they had open is gone. Show them what is left rather
        # than an empty screen about something that no longer exists.
        return replace(
            _to_list(nav), task_id=None, revision=None
        )

    if nav.screen is Screen.CONFIRMATION and task.revision != nav.revision:
        # It changed underneath a pending confirmation. Never act on a
        # stale representation: send them back to read it again.
        return replace(
            nav,
            screen=Screen.TASK_DETAIL,
            action_id=None,
            page=0,
            revision=task.revision,
            stale=True,
        )

    return nav

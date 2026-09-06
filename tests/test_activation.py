"""Every control obeys the wearer's activation setting.

This exists because two screens did not. The count card and the action
menu each built their Button directly rather than through the shared
builders, so they silently kept the framework's defaults -- a 1.5 second
fill dwell. On those two screens, resting your gaze pressed the control,
whatever the wearer had chosen.

That is the one thing this app says it will never do, and reading the code
was not enough to notice: the builders it was supposed to go through were
all correct. So these checks look at the widgets that actually get built,
not at the code that is supposed to build them.
"""

import pytest

from agent_hud.tasks import Action, Task

pytest.importorskip(
    "raven_framework", reason="Raven framework not installed — screen tests skipped"
)

from agent_hud.screens import parts
from agent_hud.screens.action_menu import build_action_menu
from agent_hud.screens.attention import build_attention
from agent_hud.screens.confirmation import build_confirmation
from agent_hud.screens.task_detail import build_task_detail
from agent_hud.screens.task_list import build_task_list

TASK = Task(
    id="t1",
    revision=1,
    source="Claude",
    title="Deploy production",
    summary="Deployment needs approval",
    detail="Nothing surprising in this one.",
    needs_you=True,
    primary=Action(id="approve", label="Approve"),
    secondary=Action(id="reject", label="Reject"),
)


def _noop(*args, **kwargs):
    return None


def _stare_seconds(button) -> float:
    """How long a gaze must rest on a button before it fires."""
    return (button.max_progress / button.progress_increment) / button.fps


def _buttons(widget):
    from raven_framework.components.button import Button

    if isinstance(widget, Button):
        return [widget]
    return widget.findChildren(Button)


def _all_screens():
    return {
        "attention": build_attention(2, on_open=_noop, on_later=_noop),
        "task list": build_task_list([TASK], on_select=_noop, on_later=_noop),
        "task detail": build_task_detail(
            TASK,
            page=0,
            on_back=_noop,
            on_take_action=_noop,
            on_scroll_up=_noop,
            on_scroll_down=_noop,
        ),
        "action menu": build_action_menu(
            TASK,
            on_primary=_noop,
            on_secondary=_noop,
            on_audio=_noop,
            on_cancel=_noop,
            audio_available=True,
        ),
        "confirmation": build_confirmation(
            TASK, TASK.primary, on_ok=_noop, on_cancel=_noop
        ),
    }


@pytest.fixture(autouse=True)
def _restore_default_activation():
    yield
    parts.set_activation("double_blink", 1500)


def test_double_blink_means_looking_never_presses(qapp):
    parts.set_activation("double_blink", 1500)

    checked = 0
    for name, widget in _all_screens().items():
        buttons = _buttons(widget)
        assert buttons, f"{name}: no buttons found, so this checks nothing"
        for button in buttons:
            assert button.use_fill_dwell is False, (
                f"{name}: a control shows a dwell fill while the wearer "
                "chose double blink"
            )
            assert _stare_seconds(button) > 30, (
                f"{name}: a control fires after only "
                f"{_stare_seconds(button):.1f}s of being looked at"
            )
            checked += 1
    assert checked >= 8, f"only {checked} controls examined"


def test_choosing_dwell_reaches_every_screen(qapp):
    """The other half. A setting only half wired is its own bug."""
    parts.set_activation("dwell", 1200)

    # Only the timing is asserted, not how the progress is drawn. The
    # filled primary button deliberately shows an outline ring instead:
    # the fill dwell would throw away the background colour that makes it
    # the filled one. Both are dwell; they just look different.
    for name, widget in _all_screens().items():
        for button in _buttons(widget):
            assert _stare_seconds(button) < 5, (
                f"{name}: dwell was chosen but a control still needs "
                f"{_stare_seconds(button):.1f}s"
            )


def test_the_screens_agree_with_each_other(qapp):
    """No screen may be more eager than its neighbours."""
    parts.set_activation("double_blink", 1500)
    times = {
        name: {round(_stare_seconds(b), 1) for b in _buttons(widget)}
        for name, widget in _all_screens().items()
    }
    distinct = set().union(*times.values())
    assert len(distinct) == 1, f"screens disagree: {times}"


# --- setting one control apart from the rest ---------------------------


def _fastest(widget) -> float:
    return min(_stare_seconds(b) for b in _buttons(widget))


def _slowest(widget) -> float:
    return max(_stare_seconds(b) for b in _buttons(widget))


def test_one_control_can_be_held_back_while_the_rest_use_dwell(qapp):
    """The case this exists for: browse with your eyes, but never send
    anything without a deliberate gesture."""
    parts.set_activation("dwell", 1200, {"confirm": "double_blink"})

    confirmation = build_confirmation(TASK, TASK.primary, on_ok=_noop, on_cancel=_noop)
    times = sorted(round(_stare_seconds(b), 1) for b in _buttons(confirmation))
    assert times[0] < 5, "Cancel should still follow the global dwell"
    assert times[-1] > 30, "Confirm was set apart and must not dwell"


def test_a_control_can_be_singled_out_for_dwell_instead(qapp):
    """And the other direction: mostly deliberate, with one exception."""
    parts.set_activation("double_blink", 1200, {"open_task": "dwell"})

    rows = build_task_list([TASK], on_select=_noop, on_later=_noop)
    assert _fastest(rows) < 5, "the task row was set to dwell"
    assert _slowest(rows) > 30, "Later was not, and must be unaffected"


def test_each_role_reaches_only_its_own_control(qapp):
    """A role that quietly covers more than it names is worse than none:
    the wearer would be changing controls they never asked about."""
    from agent_hud.preferences import CONTROL_ROLES

    screens_for = {
        "open_list": lambda: build_attention(2, on_open=_noop, on_later=_noop),
        "set_aside": lambda: build_attention(2, on_open=_noop, on_later=_noop),
        "open_task": lambda: build_task_list([TASK], on_select=_noop, on_later=_noop),
        "back": lambda: build_task_detail(TASK, page=0, on_back=_noop),
        "take_action": lambda: build_task_detail(
            TASK, page=0, on_back=_noop, on_take_action=_noop
        ),
        "confirm": lambda: build_confirmation(
            TASK, TASK.primary, on_ok=_noop, on_cancel=_noop
        ),
        "cancel": lambda: build_confirmation(
            TASK, TASK.primary, on_ok=_noop, on_cancel=_noop
        ),
    }

    for role, build in screens_for.items():
        parts.set_activation("double_blink", 1200, {role: "dwell"})
        widget = build()
        quick = [b for b in _buttons(widget) if _stare_seconds(b) < 5]
        assert len(quick) == 1, (
            f"role {role!r} changed {len(quick)} controls on its screen, "
            "expected exactly one"
        )

    # And every role is a real one the glasses know about.
    for role in CONTROL_ROLES:
        parts.set_activation("double_blink", 1200, {role: "dwell"})
        assert parts.activation(role)["use_fill_dwell"] is True

"""Speaking a reply, and reading back what was heard.

Three screens for one act: listening, waiting for the words, and checking
them before anything is sent.

The check is the point. Speech recognition gets things wrong, and a
wearer who dictates "do not deploy" and has "now deploy" sent on their
behalf has been failed badly. So the transcript comes back, is read, and
only then can be sent — the same two-step shape every other action has.

If it came back wrong, the way out is to say it again. There is no gaze
text editor here and there will not be one: fixing a sentence by staring
at letters is miserable, and the phone is right there for the times when
the exact words matter.
"""

from __future__ import annotations

from collections.abc import Callable

from raven_framework.components.vertical_container import VerticalContainer

from ..tasks import Task
from . import parts
from . import style as s

CARD_WIDTH = 480
INNER_WIDTH = CARD_WIDTH - s.CARD_MARGIN * 2


def build_listening(
    task: Task,
    *,
    seconds_left: int | None = None,
    on_done: Callable[[], None],
    on_cancel: Callable[[], None],
) -> VerticalContainer:
    """Recording. Says so plainly, because a microphone that is on should
    never be a thing you have to infer.

    The screen says what actually happens: you press Done. It does not
    claim to notice you stopping talking, because it cannot -- the
    framework hands over the audio only when recording ends, so there is
    no level to watch. What it does have is a cap, so a recording
    somebody forgot about cannot run for ever.
    """
    card = parts.card(CARD_WIDTH, spacing=10)
    card.add(parts.label("Listening", width=INNER_WIDTH))
    card.add(parts.title(task.title, width=INNER_WIDTH))
    card.add(
        parts.body(
            "Say your reply, then press Done.",
            INNER_WIDTH,
        )
    )
    if seconds_left is not None:
        card.add(
            parts.small(
                f"Stops on its own in {seconds_left}s",
                width=INNER_WIDTH,
                align="left",
            )
        )
    card.add(
        parts.button_row(
            INNER_WIDTH,
            [
                parts.secondary_button("Cancel", on_cancel, width=150),
                parts.primary_button("Done", on_done, width=170),
            ],
        )
    )
    return card


def build_processing(
    task: Task, *, on_cancel: Callable[[], None]
) -> VerticalContainer:
    """Waiting for the gateway to turn the recording into words."""
    card = parts.card(CARD_WIDTH, spacing=10)
    card.add(parts.label("Working it out", width=INNER_WIDTH))
    card.add(parts.title(task.title, width=INNER_WIDTH))
    card.add(
        parts.body(
            "Turning what you said into words. This happens on your own "
            "gateway; the recording goes nowhere else and is dropped as "
            "soon as it has been read.",
            INNER_WIDTH,
        )
    )
    card.add(
        parts.button_row(
            INNER_WIDTH,
            [parts.secondary_button("Cancel", on_cancel, width=150)],
        )
    )
    return card


def build_review(
    task: Task,
    text: str,
    *,
    failed_reason: str = "",
    on_again: Callable[[], None],
    on_send: Callable[[], None],
) -> VerticalContainer:
    """What was heard, before any of it leaves.

    Args:
        text: The transcript. Shown as it will be sent, not summarised.
        failed_reason: Set when there was nothing to review — no engine,
            nothing heard, or the gateway could not be reached. The screen
            then offers only another attempt, because there is nothing to
            send and pretending otherwise would be the worst option.
    """
    card = parts.card(CARD_WIDTH, spacing=10)

    if failed_reason:
        card.add(parts.label("Not heard", width=INNER_WIDTH))
        card.add(parts.title(task.title, width=INNER_WIDTH))
        card.add(parts.body(failed_reason, INNER_WIDTH))
        card.add(
            parts.button_row(
                INNER_WIDTH,
                [parts.primary_button("Say it again", on_again, width=200)],
            )
        )
        return card

    card.add(parts.label("You said", width=INNER_WIDTH))
    card.add(parts.rule(INNER_WIDTH))
    card.add(parts.body(text, INNER_WIDTH))
    card.add(parts.rule(INNER_WIDTH))
    card.add(
        parts.small(
            f"Will be sent to {task.source}", width=INNER_WIDTH, align="left"
        )
    )
    card.add(
        parts.button_row(
            INNER_WIDTH,
            [
                parts.secondary_button("Say it again", on_again, width=190),
                parts.primary_button("Send", on_send, width=150),
            ],
        )
    )
    return card


__all__ = ["CARD_WIDTH", "build_listening", "build_processing", "build_review"]

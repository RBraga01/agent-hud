"""Screen 7 — what became of the answer.

The wording here is the most carefully chosen in the app, because this is
the screen someone reads and then walks away from.

**"Sent" means the gateway accepted the request.** Nothing more. It does
not mean the deployment happened, the tests reran, or the pull request
merged. Saying "Approved" or "Done" here would be claiming an outcome
nobody has confirmed, and a wearer who trusts it and stops paying
attention is worse off than one who was told the truth.

If we do not know whether it arrived, the screen says so and offers to
try again with the same request id, so a gateway that did receive the
first attempt recognises the second rather than acting twice.
"""

from __future__ import annotations

from collections.abc import Callable
from enum import Enum

from raven_framework.components.vertical_container import VerticalContainer

from ..tasks import Task
from . import parts
from . import style as s

CARD_WIDTH = 460
INNER_WIDTH = CARD_WIDTH - s.CARD_MARGIN * 2


class SendState(str, Enum):
    """How far one answer has got.

    Attributes:
        SENDING: In flight. We know nothing yet.
        SENT: The gateway accepted the request.
        FAILED: We do not know whether it arrived. Worth trying again.
        REFUSED: The gateway heard it and will not take it. Trying again
            unchanged would just ask twice.
        STALE: The task moved on. The wearer has to read it again.
        UNAVAILABLE: There is no send path at all in this build.
    """

    SENDING = "sending"
    SENT = "sent"
    FAILED = "failed"
    REFUSED = "refused"
    STALE = "stale"
    UNAVAILABLE = "unavailable"


# Heading, then the sentence under it. Deliberately plain: no jargon, no
# status codes, and never a claim about what the agent did.
_WORDS = {
    SendState.SENDING: (
        "Sending",
        "Waiting for the gateway to take it.",
    ),
    SendState.SENT: (
        "Sent",
        "The gateway took your answer. What it does next will show up in "
        "the list when it has happened.",
    ),
    SendState.FAILED: (
        "Not sent",
        "The gateway could not be reached, so it is not known whether your "
        "answer arrived. Trying again is safe: it will not be acted on twice.",
    ),
    SendState.REFUSED: (
        "Not sent",
        "The gateway would not take this answer.",
    ),
    SendState.STALE: (
        "Task changed",
        "This task moved on while you were deciding, so nothing was sent. "
        "Read it again before answering.",
    ),
    SendState.UNAVAILABLE: (
        "Not sent",
        "This version can show you what is waiting and let you choose what "
        "to do, but it cannot send an answer back yet.",
    ),
}


def build_result(
    state: SendState,
    *,
    task: Task | None = None,
    reason: str = "",
    on_back: Callable[[], None],
    on_retry: Callable[[], None] | None = None,
    on_read_again: Callable[[], None] | None = None,
) -> VerticalContainer:
    """Say what happened, in terms nobody has to interpret.

    Args:
        state: How far the answer got.
        task: What it was about, named so the screen is not ambiguous.
        reason: The gateway's own words, shown only when it refused.
        on_retry: Offered only for ``FAILED`` — the one state where we
            genuinely do not know and asking again is safe.
        on_read_again: Offered for ``STALE``.
    """
    heading, sentence = _WORDS[state]

    card = parts.card(CARD_WIDTH, spacing=10)
    card.add(parts.label(heading, width=INNER_WIDTH))
    if task is not None:
        card.add(parts.title(task.title, width=INNER_WIDTH))
    card.add(parts.body(sentence, INNER_WIDTH))

    # The gateway's own explanation, when it gave one. Only on a refusal:
    # anywhere else it would be technical noise on a face.
    if state is SendState.REFUSED and reason:
        card.add(parts.small(reason, width=INNER_WIDTH, align="left"))

    buttons = [parts.secondary_button("Back", on_back, width=150)]
    if state is SendState.FAILED and on_retry is not None:
        buttons.append(parts.primary_button("Try again", on_retry, width=180))
    if state is SendState.STALE and on_read_again is not None:
        buttons.append(parts.primary_button("Read it", on_read_again, width=180))
    card.add(parts.button_row(INNER_WIDTH, buttons))

    return card


__all__ = ["CARD_WIDTH", "SendState", "build_result"]

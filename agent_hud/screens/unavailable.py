"""Screen — the gateway is not answering.

The last known list stays on screen with an amber marker for a while,
because a wobbly network is not worth interrupting anyone over. But
presenting stale work as current for ever would be its own kind of lie,
so once it is clear nobody is there the display says so plainly.

Switching to another paired gateway is offered here and **only** here, as
something the wearer presses. The glasses never switch by themselves.
Falling back from Work to Home would put one environment's tasks in front
of somebody who believed they were looking at the other's, which is worse
than showing nothing.
"""

from __future__ import annotations

from collections.abc import Callable

from raven_framework.components.vertical_container import VerticalContainer

from ..gateways import Gateway
from . import parts
from . import style as s

CARD_WIDTH = 450
INNER_WIDTH = CARD_WIDTH - s.CARD_MARGIN * 2


def build_unavailable(
    gateway: Gateway,
    *,
    others: tuple[Gateway, ...] = (),
    retrying: bool = False,
    on_retry: Callable[[], None],
    on_switch: Callable[[str], None] | None = None,
) -> VerticalContainer:
    """Say which gateway is missing, and offer the two honest ways out.

    Args:
        gateway: The one that is not answering, named so it is obvious
            which environment has gone quiet.
        others: Gateways already paired with these glasses. Only ever
            these — there is no discovery here, and nothing appears that
            the wearer did not set up themselves.
        retrying: True while an attempt is in flight, so the button does
            not look ignored.
    """
    card = parts.card(CARD_WIDTH, spacing=10)

    card.add(parts.label("Gateway unavailable", width=INNER_WIDTH))
    card.add(parts.title(gateway.name, width=INNER_WIDTH))
    card.add(
        parts.body(
            "Trying to reach it again."
            if retrying
            else "Nothing has answered for a while, so what was on screen "
            "may be out of date.",
            INNER_WIDTH,
        )
    )

    if others:
        card.add(parts.rule(INNER_WIDTH))
        card.add(
            parts.small("Switch to", width=INNER_WIDTH, align="left")
        )
        for other in others:
            card.add(
                parts.row_button(
                    other.name,
                    "",
                    (lambda name=other.name: on_switch(name))
                    if on_switch is not None
                    else None,
                    width=INNER_WIDTH,
                )
            )

    card.add(
        parts.button_row(
            INNER_WIDTH,
            [parts.primary_button("Try again", on_retry, width=190)],
        )
    )
    return card


__all__ = ["CARD_WIDTH", "build_unavailable"]

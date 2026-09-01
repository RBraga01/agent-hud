"""Fetching the current list from the gateway.

This module never raises. Every failure comes back as an empty list with
a reason attached, because an unhandled exception on the glasses means a
blank display, and a blank display is indistinguishable from "nothing
needs you" — the one thing this app must never get wrong.

Uses `requests`, which the Raven framework already bundles. Nothing here
adds a dependency, because how extra packages get installed onto the
glasses is undocumented.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import requests

from .items import Item, parse_payload

DEFAULT_TIMEOUT_SECONDS = 5.0


@dataclass(frozen=True)
class FetchResult:
    """What came back, and whether the gateway could be reached at all.

    Attributes:
        items: Parsed items. Empty when the fetch failed.
        ok: True when the gateway answered with something usable.
        reason: Why it failed, for logging. Empty when ok.
        dropped: Entries in an otherwise good response that did not match
            the contract and were discarded. Above zero means what you are
            looking at has holes in it.
    """

    items: list[Item] = field(default_factory=list)
    ok: bool = True
    reason: str = ""
    dropped: int = 0


def fetch_items(
    url: str, timeout: float = DEFAULT_TIMEOUT_SECONDS
) -> FetchResult:
    """Ask the gateway for the current list.

    Three outcomes, deliberately kept apart:

    * Could not reach or could not read the gateway: ok is False.
    * The gateway answered with something that is not a list of items:
      also ok is False. It is talking nonsense, and reporting that as
      "nothing needs you" would be the worst thing this could do.
    * The gateway answered properly: ok is True. Individual entries that
      did not match the contract are dropped and counted, because a list
      with holes in it is not the same as a complete one.
    """
    try:
        response = requests.get(url, timeout=timeout)
    except requests.RequestException as exc:
        return FetchResult(ok=False, reason=f"could not reach gateway: {exc}")

    if response.status_code != 200:
        return FetchResult(
            ok=False, reason=f"gateway returned {response.status_code}"
        )

    try:
        payload = response.json()
    except ValueError as exc:
        return FetchResult(ok=False, reason=f"gateway sent unreadable data: {exc}")

    parsed = parse_payload(payload)
    if not parsed.valid:
        return FetchResult(
            ok=False, reason="gateway did not send a list of items"
        )

    return FetchResult(items=parsed.items, ok=True, dropped=parsed.dropped)

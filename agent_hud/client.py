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

from .items import Item, parse_items

DEFAULT_TIMEOUT_SECONDS = 5.0


@dataclass(frozen=True)
class FetchResult:
    """What came back, and whether the gateway could be reached at all.

    Attributes:
        items: Parsed items. Empty when the fetch failed.
        ok: True when the gateway answered with something usable.
        reason: Why it failed, for logging. Empty when ok.
    """

    items: list[Item] = field(default_factory=list)
    ok: bool = True
    reason: str = ""


def fetch_items(
    url: str, timeout: float = DEFAULT_TIMEOUT_SECONDS
) -> FetchResult:
    """Ask the gateway for the current list.

    A malformed entry inside an otherwise valid response is not a
    failure — it is dropped by the parser and the rest is kept. Only a
    gateway we could not reach or could not understand counts as failure.
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

    return FetchResult(items=parse_items(payload), ok=True)

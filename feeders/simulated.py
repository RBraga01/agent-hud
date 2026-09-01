"""Invented items, for demonstrating and testing without any accounts.

This stands in for the sources that would otherwise need your own data:
pull requests, build results, and agents running elsewhere. Everything
here is made up. It names no real account, repository or address, and it
reaches nothing over the network.

It is deliberately the same every time. Screenshots and tests both depend
on it not drifting.
"""

from __future__ import annotations

# Written to look like a real morning: a couple of things genuinely
# waiting, and a couple quietly getting on with it.
_ITEMS: tuple[dict, ...] = (
    {
        "id": "sim-review",
        "title": "PR 38",
        "detail": "review requested",
        "needs_you": True,
    },
    {
        "id": "sim-build",
        "title": "Build",
        "detail": "failed on main",
        "needs_you": True,
    },
    {
        "id": "sim-approval",
        "title": "Deploy",
        "detail": "waiting for approval",
        "needs_you": True,
    },
    {
        "id": "sim-tests",
        "title": "Tests",
        "detail": "running, 84 of 91",
        "needs_you": False,
    },
    {
        "id": "sim-agent",
        "title": "Codex",
        "detail": "working on the parser",
        "needs_you": False,
    },
)


def collect() -> list[dict]:
    """The invented list. Copies, so a caller cannot alter the originals."""
    return [dict(item) for item in _ITEMS]

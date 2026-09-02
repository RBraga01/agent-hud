"""Invented tasks, for demonstrating and testing without any accounts.

This stands in for the sources that would otherwise need your own data:
pull requests, build results, deployments, and agents running elsewhere.
Everything here is made up. It names no real account, repository or
address, and it reaches nothing over the network.

It is deliberately the same every time. Screenshots and tests both depend
on it not drifting.

This is also the only feeder that offers actions, because it is the only
one whose "gateway" can pretend to carry them out. The feeders that read
real tools offer none until there is a real path to act on them — the
display never shows a button it cannot honour.
"""

from __future__ import annotations

# Written to look like a real morning: a few things genuinely waiting,
# and a couple quietly getting on with it.
_TASKS: tuple[dict, ...] = (
    {
        "id": "sim-approval",
        "revision": 4,
        "source": "Claude",
        "title": "Deploy production",
        "summary": "Deployment needs approval",
        "detail": (
            "Validation completed. 47 tests passed. Production deployment "
            "is waiting for your approval.\n\n"
            "The change updates the checkout service and adds a retry to "
            "the payment callback. Nothing else in the release touches "
            "customer data.\n\n"
            "Rolling back takes about two minutes if it goes wrong."
        ),
        "needs_you": True,
        "actions": {
            "primary": {"id": "approve", "label": "Approve"},
            "secondary": {"id": "reject", "label": "Reject"},
        },
    },
    {
        "id": "sim-build",
        "revision": 2,
        "source": "Codex",
        "title": "Integration tests",
        "summary": "2 integration tests failed",
        "detail": (
            "Two tests failed on the parser branch. Both are in the date "
            "handling, and both passed on the previous run."
        ),
        "needs_you": True,
        "actions": {"primary": {"id": "rerun", "label": "Rerun"}},
    },
    {
        "id": "sim-review",
        "revision": 1,
        "source": "GitHub",
        "title": "PR 38",
        "summary": "Review requested",
        "detail": (
            "A review was requested on pull request 38, which renames the "
            "settings module and updates everything that imported it."
        ),
        "needs_you": True,
    },
    {
        "id": "sim-tests",
        "revision": 9,
        "source": "Codex",
        "title": "Test run",
        "summary": "Running, 84 of 91",
        "detail": "Still going. Nothing has failed so far.",
        "needs_you": False,
    },
    {
        "id": "sim-agent",
        "revision": 3,
        "source": "Codex",
        "title": "Parser work",
        "summary": "Working on the parser",
        "detail": "No decisions needed yet.",
        "needs_you": False,
    },
)


def collect() -> list[dict]:
    """The invented list. Deep copies, so a caller cannot alter the originals."""
    out = []
    for task in _TASKS:
        copy = dict(task)
        if "actions" in copy:
            copy["actions"] = {
                slot: dict(action) for slot, action in copy["actions"].items()
            }
        out.append(copy)
    return out

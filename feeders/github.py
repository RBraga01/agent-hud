"""Turn "please review this" into items.

The other feeders read a log file per session and decide whose turn it is
from the last event. GitHub has no such log on disk: the state lives on
GitHub's servers. So this one asks GitHub directly, through the ``gh``
CLI, which means there is no token for this project to hold -- it reads
the auth ``gh`` already has.

It surfaces one thing: open pull requests, in any repository you can see,
where you (or a team you are on) have been asked to review. A review
request is a person waiting on you, so every item is ``needs_you``.

Draft pull requests are skipped -- there is nothing to review yet. No pull
request body or comment text is read; only the title and who opened it.

If ``gh`` is missing, not signed in, offline or rate limited, this returns
nothing rather than raising, the same as every other feeder on a bad day.
"""

from __future__ import annotations

import json
import re
import subprocess
import time
from collections.abc import Callable

from ._claude_shared import ago

# gh sorts newest-updated first; this is plenty for a glance and keeps a
# busy reviewer's list from running long.
LIMIT = 30

_FIELDS = "number,title,repository,url,updatedAt,author,isDraft"

# Everything not in this set becomes a dash, so the id is safe to drop
# straight into a URL path (the gateway slices /tasks/<id>/feedback by
# hand and never decodes it).
_UNSAFE = re.compile(r"[^a-z0-9-]+")


def _run_gh(argv: list[str]) -> tuple[int, str]:
    """Run a gh command. Returns (exit_code, stdout). Never raises."""
    try:
        done = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=15,
        )
        return done.returncode, done.stdout
    except (OSError, subprocess.SubprocessError):
        return 1, ""


def _iso_to_epoch(value: str) -> float | None:
    import datetime

    try:
        text = value.strip().replace("Z", "+00:00")
        return datetime.datetime.fromisoformat(text).timestamp()
    except ValueError:
        return None


def _slug(name_with_owner: str) -> str:
    return _UNSAFE.sub("-", name_with_owner.lower()).strip("-")


def _item(pr: dict, moment: float) -> dict | None:
    repo = pr.get("repository") or {}
    name_with_owner = str(repo.get("nameWithOwner") or "")
    number = pr.get("number")
    title = str(pr.get("title") or "").strip()
    if not name_with_owner or not isinstance(number, int) or not title:
        return None

    author = str((pr.get("author") or {}).get("login") or "someone")
    updated = _iso_to_epoch(str(pr.get("updatedAt") or "")) or moment
    when = ago(max(0.0, moment - updated))
    where = f"{name_with_owner}#{number}"

    return {
        "id": f"github-{number}-{_slug(name_with_owner)}",
        # Moves whenever the PR is touched, which is what a revision is
        # for: proof the screen still matches the source.
        "revision": int(updated),
        "source": "GitHub",
        "title": title,
        "summary": f"review requested - {where}",
        "detail": (
            f"{author} asked you to review {where}. Last updated {when}."
        ),
        "needs_you": True,
    }


def collect(
    *,
    run: Callable[[list[str]], tuple[int, str]] | None = None,
    now: float | None = None,
) -> list[dict]:
    """Open PRs awaiting your review, across every repository you can see.

    Args:
        run: Runs a command, returns (exit_code, stdout). Defaults to the
            real ``gh``; injected in tests so they never hit the network.
        now: Current time in seconds. Defaults to the real clock.
    """
    moment = time.time() if now is None else now
    runner = run or _run_gh

    code, out = runner(
        [
            "gh",
            "search",
            "prs",
            "--review-requested=@me",
            "--state=open",
            f"--limit={LIMIT}",
            f"--json={_FIELDS}",
        ]
    )
    if code != 0 or not out.strip():
        return []

    try:
        results = json.loads(out)
    except (ValueError, TypeError):
        return []
    if not isinstance(results, list):
        return []

    items = []
    for pr in results:
        if not isinstance(pr, dict) or pr.get("isDraft"):
            continue
        item = _item(pr, moment)
        if item is not None:
            items.append(item)

    return items


__all__ = ["LIMIT", "collect"]

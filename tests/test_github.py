"""Tests for the GitHub feeder.

The feeder asks GitHub, through the ``gh`` CLI, for open pull requests
awaiting your review. Every test injects a fake runner in place of ``gh``,
so nothing here touches the network or needs ``gh`` installed.
"""

import json

from agent_hud.tasks import parse_tasks
from feeders import github

NOW = 1_000_000.0


def iso(epoch: float) -> str:
    import datetime

    return (
        datetime.datetime.fromtimestamp(epoch, datetime.timezone.utc)
        .isoformat()
        .replace("+00:00", "Z")
    )


def pr(number, title, repo="octo/app", *, author="alice", draft=False, age=3600):
    return {
        "number": number,
        "title": title,
        "repository": {"name": repo.split("/")[-1], "nameWithOwner": repo},
        "url": f"https://github.com/{repo}/pull/{number}",
        "updatedAt": iso(NOW - age),
        "author": {"login": author},
        "isDraft": draft,
    }


def runner_returning(*prs, code=0):
    """A fake `gh` that returns these PRs as JSON."""

    def run(argv):
        assert argv[:3] == ["gh", "search", "prs"], argv
        assert "--review-requested=@me" in argv
        assert "--state=open" in argv
        return code, json.dumps(list(prs))

    return run


def test_a_review_request_becomes_an_item_that_needs_you():
    items = github.collect(
        run=runner_returning(pr(7, "Add retry to the uploader")), now=NOW
    )

    assert len(items) == 1
    it = items[0]
    assert it["source"] == "GitHub"
    assert it["title"] == "Add retry to the uploader"
    assert it["needs_you"] is True
    assert "octo/app#7" in it["summary"]
    assert "alice asked you to review" in it["detail"]


def test_the_id_is_stable_and_url_safe():
    one = github.collect(run=runner_returning(pr(21, "x", "RBraga01/My-Repo")), now=NOW)
    two = github.collect(run=runner_returning(pr(21, "x", "RBraga01/My-Repo")), now=NOW)

    assert one[0]["id"] == two[0]["id"]
    assert one[0]["id"] == "github-21-rbraga01-my-repo"
    assert "/" not in one[0]["id"] and "#" not in one[0]["id"]


def test_draft_pull_requests_are_skipped():
    items = github.collect(
        run=runner_returning(
            pr(1, "Real one"),
            pr(2, "Not ready", draft=True),
        ),
        now=NOW,
    )

    assert [i["title"] for i in items] == ["Real one"]


def test_several_requests_all_come_through():
    items = github.collect(
        run=runner_returning(
            pr(1, "One", "a/one"),
            pr(2, "Two", "b/two"),
            pr(3, "Three", "c/three"),
        ),
        now=NOW,
    )

    assert len(items) == 3
    assert {i["id"] for i in items} == {
        "github-1-a-one",
        "github-2-b-two",
        "github-3-c-three",
    }


def test_nothing_requested_is_an_empty_list():
    assert github.collect(run=runner_returning(), now=NOW) == []


def test_gh_missing_or_failing_is_not_fatal():
    def boom(argv):
        return 127, ""

    assert github.collect(run=boom, now=NOW) == []


def test_a_non_json_answer_is_not_fatal():
    assert github.collect(run=lambda a: (0, "not json"), now=NOW) == []


def test_a_json_object_instead_of_a_list_is_not_fatal():
    answer = (0, '{"message": "rate limited"}')
    assert github.collect(run=lambda a: answer, now=NOW) == []


def test_a_malformed_entry_is_skipped_not_fatal():
    items = github.collect(
        run=lambda a: (
            0,
            json.dumps([{"number": "not-an-int"}, pr(9, "Good one")]),
        ),
        now=NOW,
    )

    assert [i["title"] for i in items] == ["Good one"]


def test_the_revision_moves_with_the_pr():
    old = github.collect(run=runner_returning(pr(1, "x", age=86400)), now=NOW)
    new = github.collect(run=runner_returning(pr(1, "x", age=60)), now=NOW)

    assert new[0]["revision"] > old[0]["revision"]


def test_the_items_parse_as_tasks():
    items = github.collect(
        run=runner_returning(pr(7, "Add retry"), pr(8, "Fix flake")), now=NOW
    )

    tasks = parse_tasks({"tasks": items}).tasks
    assert len(tasks) == 2
    assert all(t.needs_you for t in tasks)


def test_only_the_title_and_author_are_read_no_pr_body():
    body_leak = pr(1, "Title only")
    body_leak["body"] = "secret PR description that must not surface"

    it = github.collect(run=runner_returning(body_leak), now=NOW)[0]

    blob = json.dumps(it)
    assert "secret PR description" not in blob


def test_it_is_a_known_feeder_and_dispatched():
    from agent_hud.config import KNOWN_FEEDERS, Settings
    from feeders import collect

    assert "github" in KNOWN_FEEDERS

    calls = []
    real = github.collect
    try:
        github.collect = lambda **kw: calls.append(kw) or [pr_item()]
        settings = Settings(
            gateway_url="http://x/tasks",
            poll_seconds=1.0,
            feeders=("github",),
        )
        out = collect(settings)
        assert calls, "the github feeder was never called"
        assert out and out[0]["source"] == "GitHub"
    finally:
        github.collect = real


def pr_item():
    return {
        "id": "github-1-x",
        "revision": 1,
        "source": "GitHub",
        "title": "x",
        "summary": "review requested - x#1",
        "detail": "x",
        "needs_you": True,
    }

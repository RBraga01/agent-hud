"""Tests for the feeders that produce the item list.

A feeder is the part that knows about a particular tool. The glasses app
knows about none of them, which is the whole point of the split.

The Claude reader is given a root directory rather than finding one, so
these tests build a fake session tree in a temporary folder and never
read the real home directory.
"""

import json
import time

import pytest

from agent_hud.items import parse_items
from feeders import claude_sessions, simulated

NOW = 1_000_000.0


# --- simulated --------------------------------------------------------


def test_simulated_items_match_the_contract():
    items = parse_items({"items": simulated.collect()})

    assert len(items) == len(simulated.collect())


def test_simulated_gives_something_to_look_at():
    items = simulated.collect()

    assert any(i["needs_you"] for i in items)
    assert any(not i["needs_you"] for i in items)


def test_simulated_is_the_same_every_time():
    # Screenshots and tests both depend on this not drifting.
    assert simulated.collect() == simulated.collect()


def test_simulated_invents_no_real_accounts_or_repositories():
    blob = json.dumps(simulated.collect()).lower()

    for personal in ("rbraga01", "github.com/", "http://", "https://", "@"):
        assert personal not in blob


# --- Claude sessions --------------------------------------------------


def write_session(root, project, name, entries, age_seconds):
    d = root / project
    d.mkdir(parents=True, exist_ok=True)
    f = d / f"{name}.jsonl"
    f.write_text("\n".join(json.dumps(e) for e in entries), encoding="utf-8")
    stamp = NOW - age_seconds
    import os

    os.utime(f, (stamp, stamp))
    return f


def test_a_session_waiting_on_you_needs_you(tmp_path):
    write_session(tmp_path, "c--Projects-Bookshop", "abc123",
                  [{"type": "user"}, {"type": "assistant"}], age_seconds=600)

    items = claude_sessions.collect(tmp_path, now=NOW)

    assert len(items) == 1
    assert items[0]["needs_you"] is True
    assert items[0]["title"] == "Bookshop"


def test_a_session_still_working_does_not_need_you(tmp_path):
    write_session(tmp_path, "c--Projects-Bookshop", "abc123",
                  [{"type": "assistant"}, {"type": "user"}], age_seconds=600)

    items = claude_sessions.collect(tmp_path, now=NOW)

    assert items[0]["needs_you"] is False


def test_a_session_that_just_replied_is_given_a_moment(tmp_path):
    # Claude may still be mid-turn; do not call for attention immediately.
    write_session(tmp_path, "c--Projects-Bookshop", "abc123",
                  [{"type": "assistant"}], age_seconds=5)

    assert claude_sessions.collect(tmp_path, now=NOW)[0]["needs_you"] is False


def test_an_abandoned_session_drops_out_entirely(tmp_path):
    write_session(
        tmp_path, "c--Projects-Old", "old1",
        [{"type": "assistant"}],
        age_seconds=claude_sessions.STALE_SECONDS + 60,
    )

    assert claude_sessions.collect(tmp_path, now=NOW) == []


def test_things_waiting_on_you_come_first(tmp_path):
    write_session(tmp_path, "c--Projects-Busy", "busy1",
                  [{"type": "user"}], age_seconds=300)
    write_session(tmp_path, "c--Projects-Waiting", "wait1",
                  [{"type": "assistant"}], age_seconds=300)

    items = claude_sessions.collect(tmp_path, now=NOW)

    assert items[0]["title"] == "Waiting"


def test_your_prompt_text_is_not_shown_by_default(tmp_path):
    # It is your own writing, on a display, and in a file on disk.
    write_session(tmp_path, "c--Projects-Bookshop", "abc123",
                  [{"type": "assistant"},
                   {"type": "last-prompt", "lastPrompt": "something private"}],
                  age_seconds=600)

    items = claude_sessions.collect(tmp_path, now=NOW)

    assert "something private" not in json.dumps(items)
    assert "your turn" in items[0]["detail"]


def test_your_prompt_text_appears_when_you_ask_for_it(tmp_path):
    write_session(tmp_path, "c--Projects-Bookshop", "abc123",
                  [{"type": "assistant"},
                   {"type": "last-prompt", "lastPrompt": "fix the parser"}],
                  age_seconds=600)

    items = claude_sessions.collect(tmp_path, now=NOW, show_prompts=True)

    assert "fix the parser" in items[0]["detail"]


def test_a_long_prompt_is_cut_to_fit_a_row(tmp_path):
    write_session(tmp_path, "c--Projects-Bookshop", "abc123",
                  [{"type": "assistant"},
                   {"type": "last-prompt", "lastPrompt": "x" * 200}],
                  age_seconds=600)

    detail = claude_sessions.collect(tmp_path, now=NOW, show_prompts=True)[0]["detail"]

    assert len(detail) <= claude_sessions.MAX_DETAIL + 12


def test_a_damaged_transcript_is_skipped_not_fatal(tmp_path):
    d = tmp_path / "c--Projects-Broken"
    d.mkdir(parents=True)
    f = d / "bad.jsonl"
    f.write_text("{ this is not json\nnor is this", encoding="utf-8")
    import os

    os.utime(f, (NOW - 600, NOW - 600))

    assert claude_sessions.collect(tmp_path, now=NOW) == []


def test_a_missing_projects_folder_is_not_fatal(tmp_path):
    assert claude_sessions.collect(tmp_path / "nope", now=NOW) == []


def test_every_item_matches_the_contract(tmp_path):
    write_session(tmp_path, "c--Projects-Bookshop", "abc123",
                  [{"type": "assistant"}], age_seconds=600)

    raw = claude_sessions.collect(tmp_path, now=NOW)

    assert len(parse_items({"items": raw})) == len(raw)


@pytest.mark.parametrize(
    "folder, expected",
    [
        ("d--code-api-core", "api core"),
        ("e--repos-MYAPP", "MYAPP"),
        ("e--", "E drive"),
        ("f--work-shop-front-app", "shop front app"),
    ],
)
def test_folder_names_become_readable_titles(folder, expected):
    assert claude_sessions.pretty_project(folder) == expected


def test_uses_the_real_clock_when_none_is_given(tmp_path):
    write_session(tmp_path, "c--Projects-Now", "n1",
                  [{"type": "assistant"}], age_seconds=0)
    # File is stamped at NOW, which is far in the past relative to the real
    # clock, so it should read as abandoned.
    import os

    os.utime(tmp_path / "c--Projects-Now" / "n1.jsonl", (time.time(), time.time()))

    assert len(claude_sessions.collect(tmp_path)) == 1


# --- reading a hand-edited file ---------------------------------------


def test_reads_a_hand_edited_file(tmp_path):
    from feeders import file_items

    f = tmp_path / "agents.json"
    f.write_text(json.dumps({"items": simulated.collect()[:2]}), encoding="utf-8")

    assert len(file_items(f)) == 2


def test_a_missing_file_yields_nothing(tmp_path):
    # Absent means the feeder simply has no data yet, not that anything
    # is wrong. That is calm, and calm is correct here.
    from feeders import file_items

    assert file_items(tmp_path / "nope.json") == []


def test_a_valid_file_with_no_items_is_calm(tmp_path):
    from feeders import file_items

    f = tmp_path / "agents.json"
    f.write_text(json.dumps({"items": []}), encoding="utf-8")

    assert file_items(f) == []


def test_a_typo_while_editing_is_surfaced_not_swallowed(tmp_path):
    # A file that exists but is not JSON is a broken source. Returning an
    # empty list here would show a calm, empty screen -- the one thing
    # this project must never do to hide a failure.
    from feeders import FileFeederError, file_items

    f = tmp_path / "agents.json"
    f.write_text("{ half-finished edit", encoding="utf-8")

    with pytest.raises(FileFeederError):
        file_items(f)


def test_an_empty_file_is_surfaced(tmp_path):
    from feeders import FileFeederError, file_items

    f = tmp_path / "agents.json"
    f.write_text("", encoding="utf-8")

    with pytest.raises(FileFeederError):
        file_items(f)


def test_a_broken_file_stops_collect_so_the_gateway_reports_it(tmp_path):
    # collect() lets the error propagate; stub_server turns any provider
    # exception into a 500, which the client reads as "not ok" and the
    # screen shows as incomplete. Same path a thrown claude/codex feeder
    # would take.
    from agent_hud.config import load_settings
    from feeders import FileFeederError, collect

    f = tmp_path / "agents.json"
    f.write_text("not json", encoding="utf-8")
    settings = load_settings(env={"AGENT_HUD_FEEDERS": "simulated,file"})

    with pytest.raises(FileFeederError):
        collect(settings, file_path=f)


# --- choosing feeders -------------------------------------------------


def test_collect_runs_only_the_chosen_feeders(tmp_path):
    from agent_hud.config import load_settings
    from feeders import collect

    settings = load_settings(env={"AGENT_HUD_FEEDERS": "simulated"})

    assert collect(settings) == simulated.collect()


def test_collect_keeps_the_order_the_feeders_were_listed_in(tmp_path):
    # collect() uses the real clock, so the session must be genuinely
    # recent rather than recent relative to the fake NOW.
    import os

    from agent_hud.config import load_settings
    from feeders import collect

    f = write_session(tmp_path, "c--Projects-Bookshop", "abc123",
                      [{"type": "assistant"}], age_seconds=0)
    recent = time.time() - 600
    os.utime(f, (recent, recent))

    settings = load_settings(env={
        "AGENT_HUD_FEEDERS": "claude,simulated",
        "AGENT_HUD_CLAUDE_PROJECTS": str(tmp_path),
    })

    items = collect(settings)

    assert items[0]["title"] == "Bookshop"
    assert items[-1]["id"] == simulated.collect()[-1]["id"]


def test_collect_produces_items_the_app_accepts(tmp_path):
    from agent_hud.config import load_settings
    from feeders import collect

    settings = load_settings(env={"AGENT_HUD_FEEDERS": "simulated"})
    raw = collect(settings)

    assert len(parse_items({"items": raw})) == len(raw)


def test_the_file_feeder_is_skipped_when_no_path_is_given():
    from agent_hud.config import load_settings
    from feeders import collect

    settings = load_settings(env={"AGENT_HUD_FEEDERS": "file"})

    assert collect(settings) == []


# --- readable titles, without assuming one person's folders -----------


@pytest.mark.parametrize(
    "folder, expected",
    [
        ("c--Projects-my-app", "my app"),
        ("d--code-scraper", "scraper"),
        ("e--src-parser", "parser"),
        ("e--workspace-thing", "thing"),
        ("e--Proyectos-tienda", "tienda"),
        ("e--Projekte-laden", "laden"),
        ("c--", "C drive"),
        ("d--", "D drive"),
    ],
)
def test_common_container_folders_are_dropped_whatever_the_language(folder, expected):
    assert claude_sessions.pretty_project(folder) == expected


def test_the_words_to_drop_can_be_changed():
    assert claude_sessions.pretty_project(
        "e--acme-widgets", skip_words=("acme",)
    ) == "widgets"


def test_a_folder_that_is_only_skippable_words_still_gets_a_name():
    assert claude_sessions.pretty_project("e--projects") == "E drive"


def test_the_skip_list_comes_from_settings(tmp_path):
    import os

    from agent_hud.config import load_settings
    from feeders import collect

    f = write_session(tmp_path, "e--acme-widgets", "s1",
                      [{"type": "assistant"}], age_seconds=0)
    recent = time.time() - 600
    os.utime(f, (recent, recent))

    settings = load_settings(env={
        "AGENT_HUD_FEEDERS": "claude",
        "AGENT_HUD_CLAUDE_PROJECTS": str(tmp_path),
        "AGENT_HUD_SKIP_PATH_WORDS": "acme",
    })

    assert collect(settings)[0]["title"] == "widgets"


# --- not re-reading whole transcripts ---------------------------------


def test_only_the_tail_of_a_long_transcript_is_read(tmp_path):
    """Transcripts grow without limit and are re-read on every poll.

    Reading the whole file would mean megabytes of pointless I/O every few
    seconds once a project has been going a while.
    """

    entries = [{"type": "user", "filler": "x" * 500} for _ in range(4000)]
    entries.append({"type": "assistant"})
    f = write_session(tmp_path, "c--Projects-Big", "big1", entries, age_seconds=600)

    assert f.stat().st_size > claude_sessions.TAIL_BYTES

    items = claude_sessions.collect(tmp_path, now=NOW)

    assert items[0]["needs_you"] is True


def test_a_short_transcript_is_still_read_completely(tmp_path):
    write_session(tmp_path, "c--Projects-Small", "s1",
                  [{"type": "user"}, {"type": "assistant"}], age_seconds=600)

    assert claude_sessions.collect(tmp_path, now=NOW)[0]["needs_you"] is True


# --- claude_hook through the dispatcher ------------------------------


def test_dispatcher_runs_the_claude_hook_feeder(tmp_path):
    import hashlib
    import json as _json

    from agent_hud.config import load_settings
    from feeders import collect

    state = tmp_path / "state"
    state.mkdir()
    fname = hashlib.sha256(b"s1").hexdigest()[:16] + ".json"
    (state / fname).write_text(
        _json.dumps(
            {"session_id": "s1", "project_raw": "bookshop", "state": "waiting",
             "at": time.time() - 300}
        ),
        encoding="utf-8",
    )
    settings = load_settings(env={
        "AGENT_HUD_FEEDERS": "claude_hook",
        "AGENT_HUD_CLAUDE_STATE": str(state),
    })

    items = collect(settings)

    assert len(items) == 1
    assert items[0]["title"] == "bookshop"
    assert items[0]["needs_you"] is True


def test_claude_hook_is_a_known_feeder():
    from agent_hud.config import load_settings

    s = load_settings(env={"AGENT_HUD_FEEDERS": "claude_hook,simulated"})
    assert s.feeders == ("claude_hook", "simulated")

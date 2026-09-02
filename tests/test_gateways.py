"""Tests for the paired gateways.

The rule worth most of these tests: the glasses never choose a gateway.
If the active one stops answering they say so and wait to be told what to
do. Falling back from Work to Home would put one environment's tasks in
front of someone who believed they were looking at the other's, which is
worse than showing nothing.
"""

import pytest

from agent_hud.gateways import (
    MAX_NAME,
    MAX_PROFILES,
    Gateway,
    GatewayBook,
    parse_gateways,
)

HOME = Gateway(name="Home", url="http://127.0.0.1:8765/tasks")
WORK = Gateway(name="Work", url="https://work.example/agent/tasks")
BOOK = GatewayBook(gateways=(HOME, WORK), active_name="Home")


# --- reading the configured list --------------------------------------


def test_reads_a_named_pair():
    book = parse_gateways(
        "Home=http://127.0.0.1:8765/tasks;Work=https://work.example/tasks"
    )

    assert [g.name for g in book.gateways] == ["Home", "Work"]
    assert book.gateways[1].url == "https://work.example/tasks"


def test_a_bare_address_still_works():
    book = parse_gateways("http://127.0.0.1:8765/tasks")

    assert len(book.gateways) == 1
    assert book.gateways[0].name == "Gateway"


def test_an_entry_that_is_not_an_address_is_dropped_not_guessed_at():
    book = parse_gateways("Home=not-a-url;Work=https://work.example/tasks")

    assert [g.name for g in book.gateways] == ["Work"]


def test_blank_entries_and_stray_semicolons_are_ignored():
    book = parse_gateways(";; Home=http://a.example/tasks ;;")

    assert [g.name for g in book.gateways] == ["Home"]


def test_a_repeated_name_is_kept_only_once():
    book = parse_gateways(
        "Home=http://a.example/tasks;Home=http://b.example/tasks"
    )

    assert len(book.gateways) == 1
    assert book.gateways[0].url == "http://a.example/tasks"


def test_a_very_long_name_is_cut_to_something_that_fits():
    book = parse_gateways(f"{'N' * 200}=http://a.example/tasks")

    assert len(book.gateways[0].name) == MAX_NAME


def test_the_list_does_not_grow_without_bound():
    raw = ";".join(f"G{n}=http://a{n}.example/tasks" for n in range(MAX_PROFILES + 20))

    assert len(parse_gateways(raw).gateways) == MAX_PROFILES


def test_nothing_configured_is_an_empty_book():
    book = parse_gateways("")

    assert book.gateways == ()
    assert book.active is None


# --- which one is in use ----------------------------------------------


def test_the_named_one_is_active():
    assert BOOK.active == HOME


def test_naming_nothing_uses_the_first_one():
    book = GatewayBook(gateways=(HOME, WORK))

    assert book.active == HOME


def test_naming_one_that_no_longer_exists_falls_back_to_the_first():
    # A fixed choice, not a guess: it must be the same on every start.
    book = GatewayBook(gateways=(HOME, WORK), active_name="Retired")

    assert book.active == HOME


def test_an_active_name_that_is_not_paired_is_not_kept():
    book = parse_gateways("Home=http://a.example/tasks", active="Work")

    assert book.active_name is None


def test_the_active_name_is_kept_when_it_is_real():
    book = parse_gateways(
        "Home=http://a.example/tasks;Work=http://b.example/tasks", active="Work"
    )

    assert book.active == book.gateways[1]


# --- switching is always the wearer's move ----------------------------


def test_there_is_no_way_to_fall_back_automatically():
    """The design, asserted.

    If a future change adds something that picks a gateway on failure,
    this test is the one that should stop it.
    """
    forbidden = {"failover", "fallback", "next_gateway", "auto", "choose"}
    names = {n for n in dir(GatewayBook) if not n.startswith("_")}

    assert names & forbidden == set()


def test_switching_needs_a_name_the_wearer_chose():
    switched = BOOK.switch_to("Work")

    assert switched.active == WORK


def test_switching_to_something_unpaired_changes_nothing():
    assert BOOK.switch_to("Somewhere else") == BOOK


def test_switching_leaves_the_other_gateway_paired():
    switched = BOOK.switch_to("Work")

    assert [g.name for g in switched.gateways] == ["Home", "Work"]


def test_the_switch_screen_offers_only_the_others():
    assert [g.name for g in BOOK.others()] == ["Work"]


def test_with_only_one_gateway_there_is_nowhere_to_switch():
    book = GatewayBook(gateways=(HOME,), active_name="Home")

    assert book.has_alternatives is False
    assert book.others() == ()


def test_with_two_there_is():
    assert BOOK.has_alternatives is True


def test_the_book_is_immutable():
    from dataclasses import FrozenInstanceError

    with pytest.raises(FrozenInstanceError):
        BOOK.active_name = "Work"


# --- the server root --------------------------------------------------


@pytest.mark.parametrize(
    "url, expected",
    [
        ("http://127.0.0.1:8765/tasks", "http://127.0.0.1:8765"),
        ("https://work.example/agent/hud/tasks", "https://work.example"),
        ("https://work.example", "https://work.example"),
        ("https://work.example/", "https://work.example"),
    ],
)
def test_the_root_is_taken_from_the_read_address(url, expected):
    assert Gateway(name="G", url=url).base == expected

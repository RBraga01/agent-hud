"""Tests for the item contract.

The gateway sends a list of items. This module is what the glasses trust,
so it is deliberately strict: anything that does not match the contract
exactly is dropped rather than guessed at. A malformed entry must never
be able to crash the display or silently distort the count.
"""

from dataclasses import FrozenInstanceError

import pytest

from agent_hud.items import Item, needs_you_count, parse_items, parse_payload

VALID_PAYLOAD = {
    "items": [
        {
            "id": "claude-deploy",
            "title": "Claude Code",
            "detail": "approve deploy?",
            "needs_you": True,
        },
        {
            "id": "pr-38",
            "title": "PR 38",
            "detail": "review requested",
            "needs_you": True,
        },
        {
            "id": "codex-run",
            "title": "Codex",
            "detail": "running, 84 of 91 tests",
            "needs_you": False,
        },
    ]
}


def test_parses_a_valid_payload_into_items():
    # Arrange / Act
    items = parse_items(VALID_PAYLOAD)

    # Assert
    assert len(items) == 3
    assert items[0] == Item(
        id="claude-deploy",
        title="Claude Code",
        detail="approve deploy?",
        needs_you=True,
    )


def test_preserves_the_order_the_gateway_sent():
    items = parse_items(VALID_PAYLOAD)

    assert [item.id for item in items] == ["claude-deploy", "pr-38", "codex-run"]


def test_returns_empty_list_when_items_key_is_missing():
    assert parse_items({"nothing": "here"}) == []


def test_returns_empty_list_when_items_is_not_a_list():
    assert parse_items({"items": "not a list"}) == []


def test_returns_empty_list_when_payload_is_not_a_dict():
    assert parse_items(None) == []
    assert parse_items([]) == []
    assert parse_items("garbage") == []


def test_returns_empty_list_for_an_empty_items_list():
    assert parse_items({"items": []}) == []


@pytest.mark.parametrize(
    "bad_entry, reason",
    [
        ({"title": "No id", "detail": "d", "needs_you": True}, "missing id"),
        ({"id": "a", "detail": "d", "needs_you": True}, "missing title"),
        ({"id": "a", "title": "T", "needs_you": True}, "missing detail"),
        ({"id": "a", "title": "T", "detail": "d"}, "missing needs_you"),
        ({"id": "a", "title": "", "detail": "d", "needs_you": True}, "empty title"),
        ({"id": "", "title": "T", "detail": "d", "needs_you": True}, "empty id"),
        (
            {"id": "a", "title": "T", "detail": "d", "needs_you": "true"},
            "needs_you is a string",
        ),
        (
            {"id": "a", "title": "T", "detail": "d", "needs_you": 1},
            "needs_you is a number",
        ),
        (
            {"id": "a", "title": 42, "detail": "d", "needs_you": True},
            "title is not text",
        ),
        (
            {"id": "a", "title": "T", "detail": None, "needs_you": True},
            "detail is not text",
        ),
        ("not even a dict", "entry is not an object"),
        (None, "entry is null"),
    ],
)
def test_drops_entries_that_do_not_match_the_contract(bad_entry, reason):
    payload = {"items": [bad_entry]}

    assert parse_items(payload) == [], f"should have dropped: {reason}"


def test_keeps_good_entries_when_a_bad_one_sits_between_them():
    payload = {
        "items": [
            VALID_PAYLOAD["items"][0],
            {"id": "broken", "title": "Missing detail", "needs_you": True},
            VALID_PAYLOAD["items"][2],
        ]
    }

    items = parse_items(payload)

    assert [item.id for item in items] == ["claude-deploy", "codex-run"]


def test_allows_an_empty_detail_because_some_items_have_nothing_to_add():
    payload = {"items": [{"id": "a", "title": "T", "detail": "", "needs_you": False}]}

    items = parse_items(payload)

    assert len(items) == 1
    assert items[0].detail == ""


def test_ignores_extra_fields_the_gateway_might_add_later():
    payload = {
        "items": [
            {
                "id": "a",
                "title": "T",
                "detail": "d",
                "needs_you": True,
                "future_field": "ignored",
            }
        ]
    }

    items = parse_items(payload)

    assert len(items) == 1
    assert items[0].id == "a"


def test_items_are_immutable_so_the_display_cannot_corrupt_them():
    item = parse_items(VALID_PAYLOAD)[0]

    with pytest.raises(FrozenInstanceError):
        item.title = "changed"


def test_counts_only_the_items_that_need_you():
    items = parse_items(VALID_PAYLOAD)

    assert needs_you_count(items) == 2


def test_counts_zero_for_an_empty_list():
    assert needs_you_count([]) == 0


# --- telling "empty" apart from "broken" ------------------------------
#
# The single most important distinction in this project. A display showing
# nothing must mean nothing needs you, never that the gateway is talking
# nonsense.


def test_a_valid_payload_with_no_items_is_valid():
    result = parse_payload({"items": []})

    assert result.valid is True
    assert result.items == []
    assert result.dropped == 0


def test_a_valid_payload_with_items_is_valid():
    result = parse_payload(VALID_PAYLOAD)

    assert result.valid is True
    assert len(result.items) == 3


@pytest.mark.parametrize(
    "payload",
    [
        {"something_broke": True},
        {"items": "not a list"},
        {"items": 42},
        "garbage",
        None,
        [],
        123,
    ],
)
def test_a_payload_that_is_not_a_list_of_items_is_invalid(payload):
    # Previously all of these came back as an empty list and the display
    # cheerfully reported that nothing needed you.
    result = parse_payload(payload)

    assert result.valid is False
    assert result.items == []


def test_counts_the_entries_it_had_to_throw_away():
    payload = {
        "items": [
            VALID_PAYLOAD["items"][0],
            {"id": "broken", "title": "No detail"},
            {"nonsense": True},
        ]
    }

    result = parse_payload(payload)

    assert result.valid is True
    assert len(result.items) == 1
    assert result.dropped == 2


def test_a_payload_of_entirely_bad_entries_is_still_a_valid_payload():
    # The gateway spoke the right language; its contents were wrong. That
    # is a different failure from an unreachable or nonsensical gateway,
    # and the count of discarded entries is what surfaces it.
    result = parse_payload({"items": [{"nope": 1}, {"nope": 2}]})

    assert result.valid is True
    assert result.items == []
    assert result.dropped == 2


def test_parse_items_still_returns_a_plain_list():
    # The convenience wrapper the feeders use to check their own shape.
    assert len(parse_items(VALID_PAYLOAD)) == 3

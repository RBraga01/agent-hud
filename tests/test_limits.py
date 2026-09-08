"""The per-client token bucket behind the gateway's write limiting."""

from __future__ import annotations

import pytest

from stub_server.limits import RateLimiter


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def test_a_burst_is_allowed_then_the_next_one_waits():
    clock = FakeClock()
    limiter = RateLimiter(rate=1.0, burst=3, clock=clock)

    assert [limiter.check("a") for _ in range(3)] == [True, True, True]
    assert limiter.check("a") is False


def test_tokens_come_back_at_the_configured_rate():
    clock = FakeClock()
    limiter = RateLimiter(rate=2.0, burst=2, clock=clock)

    assert limiter.check("a") and limiter.check("a")
    assert limiter.check("a") is False

    clock.advance(0.5)  # 2/s -> one token back
    assert limiter.check("a") is True
    assert limiter.check("a") is False


def test_the_bucket_never_fills_past_the_burst():
    clock = FakeClock()
    limiter = RateLimiter(rate=100.0, burst=2, clock=clock)

    clock.advance(10.0)  # would be 1000 tokens, capped at 2
    assert limiter.check("a") and limiter.check("a")
    assert limiter.check("a") is False


def test_each_client_has_its_own_bucket():
    clock = FakeClock()
    limiter = RateLimiter(rate=1.0, burst=1, clock=clock)

    assert limiter.check("a") is True
    assert limiter.check("a") is False
    # b is untouched
    assert limiter.check("b") is True


def test_rate_and_burst_must_be_positive():
    with pytest.raises(ValueError):
        RateLimiter(rate=0, burst=5)
    with pytest.raises(ValueError):
        RateLimiter(rate=5, burst=0)


def test_pruning_drops_only_the_idle_buckets():
    clock = FakeClock()
    limiter = RateLimiter(rate=1.0, burst=1, clock=clock)
    limiter._PRUNE_AT = 3  # so the sweep runs on a tiny table

    limiter.check("stale")  # seen at t=0 and never again
    clock.advance(limiter._IDLE_SECONDS + 1)
    limiter.check("fresh")  # seen just now

    # This call sees three buckets, so it sweeps first: "stale" is past
    # the idle window, "fresh" is not, and "new" is being created.
    limiter.check("new")

    assert "stale" not in limiter._buckets
    assert {"fresh", "new"} <= set(limiter._buckets)

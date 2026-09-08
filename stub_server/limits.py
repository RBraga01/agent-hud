"""Keeping one noisy client from swamping the gateway.

A gateway on loopback is talking to one machine and none of this
matters. Off loopback it is a network service, and a paired device with
a stuck retry loop -- or someone with a stolen token -- should not be
able to drown out every other request. So writes are rate limited per
client, and the whole server caps how many requests it will handle at
once. Neither limit is in the request's way until it is being abused.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass


@dataclass
class _Bucket:
    tokens: float
    seen: float


class RateLimiter:
    """A token bucket per client key.

    Each key starts with ``burst`` tokens and gains ``rate`` more every
    second, never past ``burst``. :meth:`check` takes one and says
    whether there was one to take. A steady caller under ``rate`` per
    second never notices; a burst is absorbed up to ``burst``; past that
    it is told to wait.
    """

    # Once the table is large, drop keys that have sat untouched this
    # long -- they have refilled completely and forgetting them is the
    # same as keeping them.
    _IDLE_SECONDS = 300.0
    _PRUNE_AT = 2048

    def __init__(
        self, rate: float, burst: float, *, clock=time.monotonic
    ) -> None:
        if rate <= 0 or burst <= 0:
            raise ValueError("rate and burst must both be positive")
        self._rate = float(rate)
        self._burst = float(burst)
        self._clock = clock
        self._buckets: dict[str, _Bucket] = {}
        self._lock = threading.Lock()

    def check(self, key: str) -> bool:
        """Take one token for ``key``. True if one was available."""
        now = self._clock()
        with self._lock:
            bucket = self._buckets.get(key)
            if bucket is None:
                bucket = _Bucket(tokens=self._burst, seen=now)
                self._buckets[key] = bucket
            else:
                gained = (now - bucket.seen) * self._rate
                bucket.tokens = min(self._burst, bucket.tokens + gained)
                bucket.seen = now
            # Sweep after touching this key, so the one in hand -- now
            # marked current -- is never the one dropped.
            self._prune(now)
            if bucket.tokens >= 1.0:
                bucket.tokens -= 1.0
                return True
            return False

    def _prune(self, now: float) -> None:
        if len(self._buckets) < self._PRUNE_AT:
            return
        gone = [
            key
            for key, bucket in self._buckets.items()
            if now - bucket.seen > self._IDLE_SECONDS
        ]
        for key in gone:
            del self._buckets[key]


__all__ = ["RateLimiter"]

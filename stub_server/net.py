"""Small network helpers shared by the server and its tests."""

from __future__ import annotations

import ipaddress

LOOPBACK_HOST = "127.0.0.1"

_LOOPBACK_NAMES = frozenset({"localhost", "localhost.localdomain", ""})


def is_loopback(host: str) -> bool:
    """Whether binding to ``host`` keeps the gateway on this machine only.

    An empty host, ``localhost``, and any address in 127.0.0.0/8 or ``::1``
    count. Everything else -- a LAN address, ``0.0.0.0``, a real name --
    means the gateway would be reachable from off the machine, which it is
    only allowed to be when it is locked.
    """
    name = (host or "").strip().lower()
    if name in _LOOPBACK_NAMES:
        return True
    try:
        return ipaddress.ip_address(name).is_loopback
    except ValueError:
        # A hostname we cannot resolve here. Treat it as not loopback:
        # the safe direction is to demand auth and TLS.
        return False


__all__ = ["LOOPBACK_HOST", "is_loopback"]

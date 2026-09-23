"""The gateways this pair of glasses has been paired with.

Somebody may well have two: one at home and one at work. They hold
different tasks, different credentials and different settings, and
neither needs to know the other exists. There is no account joining them
and no service in the middle — the glasses are the only thing aware of
both, which is exactly as far as that knowledge should go.

**Only one is active at a time, and switching is always something the
wearer does.** If the active gateway stops answering, the glasses say so
and offer to try again or to switch. They never switch by themselves.

That is not a limitation to be engineered around later. Falling back from
Work to Home would put one environment's tasks in front of someone who
believed they were looking at the other's, which is worse than showing
nothing at all. There is deliberately no function in this module that
chooses a gateway; every path goes through the wearer.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

MAX_NAME = 24
MAX_PROFILES = 8

_ALLOWED_SCHEMES = ("http://", "https://")


@dataclass(frozen=True)
class Gateway:
    """One paired environment.

    Attributes:
        name: What the wearer calls it. Shown when switching.
        url: Where its task list is. Answers go to the same server.
    """

    name: str
    url: str

    @property
    def base(self) -> str:
        """The server root, without the path that fetches the list."""
        marker = "://"
        start = self.url.find(marker)
        if start == -1:
            return self.url.rstrip("/")
        slash = self.url.find("/", start + len(marker))
        return (self.url if slash == -1 else self.url[:slash]).rstrip("/")


@dataclass(frozen=True)
class GatewayBook:
    """Everything paired, and which one is in use.

    Deliberately has no method that picks a gateway on its own. Look for
    one and you will not find it; that absence is the design.
    """

    gateways: tuple[Gateway, ...] = ()
    active_name: str | None = None

    @property
    def active(self) -> Gateway | None:
        """The one in use, or None when nothing is paired."""
        if not self.gateways:
            return None
        for gateway in self.gateways:
            if gateway.name == self.active_name:
                return gateway
        # Nothing named, or a name that no longer exists. The first paired
        # one is the only defensible choice, and it is a fixed one rather
        # than a guess that could differ between two starts.
        return self.gateways[0]

    @property
    def has_alternatives(self) -> bool:
        """True when there is somewhere else to switch to."""
        return len(self.gateways) > 1

    def others(self) -> tuple[Gateway, ...]:
        """The paired gateways that are not in use, in their listed order.

        This is what the switch screen offers. Already-paired only: there
        is no discovery here, and nothing appears that the wearer did not
        set up themselves.
        """
        current = self.active
        name = None if current is None else current.name
        return tuple(g for g in self.gateways if g.name != name)

    def switch_to(self, name: str) -> GatewayBook:
        """Make a different paired gateway the active one.

        Only ever called from something the wearer pressed. An unknown
        name changes nothing.
        """
        if not any(g.name == name for g in self.gateways):
            return self
        return replace(self, active_name=name)


def _clean_name(raw: str, fallback: str) -> str:
    name = " ".join(raw.split())[:MAX_NAME].strip()
    return name or fallback


def parse_gateways(raw: str, active: str | None = None) -> GatewayBook:
    """Read the paired gateways from a single configured string.

    The format is ``Name=url`` separated by semicolons, for example
    ``Home=http://127.0.0.1:8765/tasks;Work=https://work.example/tasks``.
    A bare url with no name is allowed and becomes "Gateway".

    Entries that are not usable addresses are dropped rather than guessed
    at. An entry that cannot be reached is a different problem, and one
    the display handles by saying so.
    """
    gateways: list[Gateway] = []
    seen: set[str] = set()

    for index, part in enumerate(raw.split(";")):
        part = part.strip()
        if not part:
            continue

        name, _, url = part.partition("=")
        if not url:
            name, url = "", name
        url = url.strip()
        if not url.startswith(_ALLOWED_SCHEMES):
            continue

        name = _clean_name(name, f"Gateway {index + 1}" if index else "Gateway")
        if name in seen:
            continue
        seen.add(name)

        gateways.append(Gateway(name=name, url=url))
        if len(gateways) >= MAX_PROFILES:
            break

    chosen = active.strip() if isinstance(active, str) and active.strip() else None
    if chosen is not None and not any(g.name == chosen for g in gateways):
        chosen = None

    return GatewayBook(gateways=tuple(gateways), active_name=chosen)

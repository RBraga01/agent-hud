"""Answers being written, before they are sent.

A draft is what a dictated reply becomes between being heard and being
sent. It exists so the wearer can read back what the gateway thinks they
said, and so a longer reply can be finished on a phone instead of being
fought with on a headset.

Drafts are deliberately **temporary**. They expire, they are dropped once
sent, and there is no history. This is not a conversation archive and
there is nowhere in this module to make it one: the only way a draft's
text survives is by being sent to the agent it was written for, where it
becomes part of that tool's own record rather than a second copy here.

The recording a draft came from is already gone by the time one exists.
"""

from __future__ import annotations

import secrets
import time
from dataclasses import dataclass, field, replace
from enum import Enum

# How long an unsent draft lives. Long enough to pick a phone up and
# finish the sentence; short enough that a forgotten one does not sit
# there for a week.
DRAFT_TTL_SECONDS = 30 * 60

# How many may exist at once. A wearer has one thought at a time; this is
# a bound, not a workflow.
MAX_DRAFTS = 16

MAX_TEXT = 2000


class DraftState(str, Enum):
    """Where a draft has got to.

    Attributes:
        PENDING: Written, not sent. It can still be edited or dropped.
        SENT: Handed to the agent. Kept only long enough to say so.
        DISCARDED: The wearer threw it away.
        EXPIRED: Nobody came back to it in time.
    """

    PENDING = "pending"
    SENT = "sent"
    DISCARDED = "discarded"
    EXPIRED = "expired"


@dataclass(frozen=True)
class Draft:
    """One answer being written.

    Attributes:
        id: What the glasses and the phone both refer to it by.
        task_id: What it is a reply to.
        revision: The version of that task it was written against. It
            travels with the send, so a task that moved on refuses it,
            exactly as an action would be refused.
        text: What will be sent.
        state: Where it has got to.
        created_at: When, in epoch seconds.
    """

    id: str
    task_id: str
    revision: int
    text: str
    state: DraftState = DraftState.PENDING
    created_at: float = 0.0

    @property
    def is_open(self) -> bool:
        """True while it can still be edited or sent."""
        return self.state is DraftState.PENDING


@dataclass
class DraftBook:
    """Every draft in flight. In memory, and gone when the gateway stops.

    That is not a shortcut. A draft that outlived the gateway would be a
    record of something somebody said, sitting on disk, which is exactly
    what this is not for.
    """

    ttl_seconds: float = DRAFT_TTL_SECONDS
    _drafts: dict[str, Draft] = field(default_factory=dict)

    # -- writing --------------------------------------------------------

    def create(
        self, task_id: str, revision: int, text: str, *, now: float | None = None
    ) -> Draft:
        """Start a draft from something that was just heard."""
        moment = time.time() if now is None else now
        self.expire(now=moment)

        if len(self._drafts) >= MAX_DRAFTS:
            # Drop the oldest open one. Python dicts keep insertion
            # order, so the first key is the least recently added.
            self._drafts.pop(next(iter(self._drafts)))

        draft = Draft(
            id=secrets.token_hex(8),
            task_id=task_id,
            revision=revision,
            text=text[:MAX_TEXT],
            created_at=moment,
        )
        self._drafts[draft.id] = draft
        return draft

    def edit(self, draft_id: str, text: str) -> Draft | None:
        """Replace the words. Only while it is still open."""
        draft = self._drafts.get(draft_id)
        if draft is None or not draft.is_open:
            return None
        updated = replace(draft, text=text[:MAX_TEXT])
        self._drafts[draft_id] = updated
        return updated

    def discard(self, draft_id: str) -> bool:
        """Throw it away. The text goes with it, immediately."""
        draft = self._drafts.get(draft_id)
        if draft is None:
            return False
        del self._drafts[draft_id]
        return True

    def mark_sent(self, draft_id: str) -> Draft | None:
        """Record that it went, and drop the text it carried.

        The words live in the agent's own record now. Keeping a second
        copy here would be starting the archive this is not.
        """
        draft = self._drafts.get(draft_id)
        if draft is None:
            return None
        sent = replace(draft, state=DraftState.SENT, text="")
        del self._drafts[draft_id]
        return sent

    # -- reading --------------------------------------------------------

    def get(self, draft_id: str, *, now: float | None = None) -> Draft | None:
        self.expire(now=now)
        return self._drafts.get(draft_id)

    def open_drafts(self, *, now: float | None = None) -> list[Draft]:
        """Everything still waiting to be finished, oldest first."""
        self.expire(now=now)
        return sorted(self._drafts.values(), key=lambda d: d.created_at)

    def for_task(self, task_id: str, *, now: float | None = None) -> Draft | None:
        """The open draft for one task, if there is one."""
        for draft in self.open_drafts(now=now):
            if draft.task_id == task_id:
                return draft
        return None

    def expire(self, *, now: float | None = None) -> int:
        """Drop anything nobody came back to. Returns how many went."""
        moment = time.time() if now is None else now
        gone = [
            key
            for key, draft in self._drafts.items()
            if moment - draft.created_at > self.ttl_seconds
        ]
        for key in gone:
            del self._drafts[key]
        return len(gone)

    def to_payload(self, *, now: float | None = None) -> list[dict]:
        """What the glasses and the phone are shown."""
        return [
            {
                "draft_id": draft.id,
                "task_id": draft.task_id,
                "revision": draft.revision,
                "text": draft.text,
                "state": draft.state.value,
            }
            for draft in self.open_drafts(now=now)
        ]

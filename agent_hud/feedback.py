"""Sending an answer back to the gateway.

The only part of this app that transmits anything. Everything else reads.

Two protections travel with every request, and they guard different
things:

* ``revision`` says which version of the task the wearer was looking at
  when they decided. A gateway that has already moved past it refuses the
  request. This stops someone approving a deployment whose description
  changed while they were reading it.
* ``request_id`` is the same across retries. If the first attempt reached
  the gateway and only the answer was lost, the second is recognised as
  the same request rather than approving anything twice.

The outcomes are kept strictly apart because the words on screen depend
on them. "Sent" means the gateway *accepted the request* — nothing more.
It never means the deployment happened, and the display must never say so
until a later refresh proves it.

Like the fetch, this never raises. An exception on the glasses means a
blank display, and the wearer would have no idea whether anything went.
"""

from __future__ import annotations

import json
import secrets
from dataclasses import dataclass, field
from enum import Enum

import requests

DEFAULT_TIMEOUT_SECONDS = 5.0

# The gateway's answer is a short acknowledgement. Anything larger is a
# gateway that is not behaving, and reading it would risk the memory on
# the glasses for nothing.
MAX_RESPONSE_BYTES = 64 * 1024

# The longest message the glasses will send. Anything the wearer dictates
# is trimmed here, at the boundary, rather than somewhere further in.
MAX_TEXT = 2000

_REQUEST_ID_BYTES = 16


class SendOutcome(str, Enum):
    """What became of one attempt to send.

    Attributes:
        ACCEPTED: The gateway took the request. It has not necessarily
            finished carrying it out, and the screen must not imply it has.
        STALE: The gateway heard it and refused, because the task has
            moved on. Not a network failure; retrying unchanged is wrong.
        REJECTED: The gateway will not accept this at all — an action it
            does not offer, or a request it could not read. Retrying
            unchanged is pointless.
        UNREACHABLE: We do not know whether it arrived. This is the only
            outcome that should be retried, and only with the same id.
    """

    ACCEPTED = "accepted"
    STALE = "stale"
    REJECTED = "rejected"
    UNREACHABLE = "unreachable"


@dataclass(frozen=True)
class Feedback:
    """One answer, ready to send.

    Attributes:
        task_id: Which task. The gateway maps this to whatever session it
            belongs to; the glasses never learn or send that.
        revision: The version the wearer was looking at when they decided.
        action_id: An action the gateway itself offered. Never invented.
        text: A dictated message, as an alternative to an action.
        request_id: Stable across retries of this same answer.
    """

    task_id: str
    revision: int
    request_id: str
    action_id: str | None = None
    text: str | None = None

    @property
    def kind(self) -> str:
        return "action" if self.action_id is not None else "message"

    def body(self) -> dict:
        """The JSON the gateway receives. Nothing else goes with it."""
        payload = {
            "revision": self.revision,
            "type": self.kind,
            "request_id": self.request_id,
        }
        if self.action_id is not None:
            payload["action_id"] = self.action_id
        else:
            payload["text"] = (self.text or "")[:MAX_TEXT]
        return payload


@dataclass(frozen=True)
class SendResult:
    """What happened, in the only terms the screen is allowed to use."""

    outcome: SendOutcome
    reason: str = ""
    request_id: str = ""
    fields: dict = field(default_factory=dict)

    @property
    def is_sent(self) -> bool:
        """True only when the gateway said it took the request."""
        return self.outcome is SendOutcome.ACCEPTED

    @property
    def can_retry(self) -> bool:
        """True only when we genuinely do not know whether it arrived.

        A stale or rejected answer means the gateway heard us and said no.
        Sending it again unchanged would just be asking twice.
        """
        return self.outcome is SendOutcome.UNREACHABLE


def new_request_id() -> str:
    """A fresh id for one answer.

    Random, and nothing else. It travels to the gateway, so it must carry
    nothing about the wearer, the machine or what they are doing.
    """
    return secrets.token_hex(_REQUEST_ID_BYTES)


# Which HTTP answers mean what. Anything not listed, and any 5xx, is
# treated as "we do not know", which is the only safe default: it is the
# one outcome that leads to a retry rather than a claim.
_OUTCOMES = {
    200: SendOutcome.ACCEPTED,
    201: SendOutcome.ACCEPTED,
    202: SendOutcome.ACCEPTED,
    204: SendOutcome.ACCEPTED,
    400: SendOutcome.REJECTED,
    404: SendOutcome.REJECTED,
    409: SendOutcome.STALE,
    422: SendOutcome.REJECTED,
}


DEVICE_HEADER = "X-Agent-Hud-Device"


def send_feedback(
    base_url: str,
    feedback: Feedback,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    device_token: str = "",
) -> SendResult:
    """Send one answer. Never raises.

    Args:
        base_url: The gateway's root, without a path.
        feedback: What to send.
        timeout: Seconds to wait.

    Returns:
        A result whose outcome decides what the screen is allowed to say.
    """
    if feedback.action_id is None and not (feedback.text or "").strip():
        # Nothing the gateway could act on. Refuse here rather than send
        # an empty request and interpret whatever comes back.
        return SendResult(
            outcome=SendOutcome.REJECTED,
            reason="nothing to send",
            request_id=feedback.request_id,
        )

    url = f"{base_url.rstrip('/')}/tasks/{feedback.task_id}/feedback"

    try:
        response = requests.post(
            url,
            json=feedback.body(),
            timeout=timeout,
            stream=True,
            headers=(
                {DEVICE_HEADER: device_token} if device_token else {}
            ),
        )
    except requests.RequestException as exc:
        return SendResult(
            outcome=SendOutcome.UNREACHABLE,
            reason=f"could not reach gateway: {exc}",
            request_id=feedback.request_id,
        )

    try:
        outcome = _OUTCOMES.get(response.status_code, SendOutcome.UNREACHABLE)

        try:
            body = response.raw.read(MAX_RESPONSE_BYTES + 1, decode_content=True)
        except Exception as exc:  # a stalled body, however it surfaces
            return SendResult(
                outcome=SendOutcome.UNREACHABLE,
                reason=f"could not read gateway: {exc}",
                request_id=feedback.request_id,
            )

        if len(body) > MAX_RESPONSE_BYTES:
            return SendResult(
                outcome=SendOutcome.UNREACHABLE,
                reason=f"gateway answer over {MAX_RESPONSE_BYTES // 1024} KB",
                request_id=feedback.request_id,
            )
    finally:
        response.close()

    # The answer's contents are a courtesy. The status code is what
    # decides the outcome, so an unreadable body never turns an accepted
    # request into a claimed failure.
    fields: dict = {}
    try:
        parsed = json.loads(body) if body else {}
        if isinstance(parsed, dict):
            fields = parsed
    except ValueError:
        fields = {}

    reason = ""
    if outcome is not SendOutcome.ACCEPTED:
        reason = str(
            fields.get("error")
            or fields.get("status")
            or f"gateway returned {response.status_code}"
        )

    return SendResult(
        outcome=outcome,
        reason=reason,
        request_id=feedback.request_id,
        fields=fields,
    )

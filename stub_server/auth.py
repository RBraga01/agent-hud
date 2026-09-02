"""Who is allowed to talk to this gateway.

The gateway serves whatever your agents are doing and accepts answers on
your behalf. On loopback that needs nothing in front of it. Anywhere else
it needs a lock, and this is the lock.

**Passkeys, not passwords.** The phone or laptop holds a private key and
proves it holds it. What arrives here is a public key and a signature.
There is no password to reuse, nothing to phish, and nothing worth
stealing from this machine's disk.

**No biometric ever reaches this code.** The fingerprint or the face
unlocks the key on the device that owns it. This gateway is not told
which, is not told whether one was used, and could not store one if it
wanted to — there is nowhere here that a template could go.

The ceremonies are not hand-rolled. Verifying a WebAuthn signature means
parsing COSE keys, checking attestation and getting a dozen small things
right, and a subtly wrong implementation is worse than none because it
looks like a lock. ``py_webauthn`` does that part. What is written here is
the policy around it: what to store, how long a session lasts, and what
happens when it expires.

Off unless switched on, and the gateway refuses to leave loopback either
way — turning this on is what will make leaving loopback defensible, not
something that does it automatically.
"""

from __future__ import annotations

import hashlib
import json
import secrets
import time
from dataclasses import dataclass, field
from pathlib import Path

# How long a browser stays signed in. Long enough not to be a nuisance
# on a phone you pick up through the day; short enough that a borrowed
# laptop does not stay signed in for a week.
SESSION_SECONDS = 12 * 3600

# How long a challenge is good for. A ceremony takes seconds; anything
# older is either lost or somebody's replay.
CHALLENGE_SECONDS = 120

# Sensitive administration asks for the passkey again even inside a live
# session: pairing a device, revoking one, adding an authenticator.
FRESH_SECONDS = 5 * 60

MAX_CREDENTIALS = 16
MAX_DEVICES = 8


class AuthUnavailable(RuntimeError):
    """Authentication was asked for and the library is not installed."""


@dataclass(frozen=True)
class Credential:
    """One registered passkey.

    Everything here is public. There is deliberately no field that could
    hold a secret, a password or anything derived from a fingerprint.

    Attributes:
        credential_id: What the authenticator calls this key.
        public_key: The public half. The private half never leaves the
            device that made it.
        sign_count: The authenticator's own counter, used to notice a
            cloned key.
        name: What the person called this device.
        created_at: When it was registered, in epoch seconds.
    """

    credential_id: str
    public_key: str
    sign_count: int
    name: str
    created_at: float


@dataclass(frozen=True)
class Device:
    """A paired pair of glasses, or anything else that reads the list.

    The glasses cannot do a passkey ceremony: there is no browser on them
    and no sensor to prove anything with. So they get a token instead,
    issued from Control by somebody who has just proved themselves, and
    revocable there.

    Only the hash is kept. The token itself is shown once, when it is
    made, and after that this machine cannot produce it either -- so a
    copy of this file is not a way in.

    Attributes:
        device_id: What Control lists it as.
        token_hash: The hash of the token. Never the token.
        name: What the person called it.
        created_at: When it was paired.
        last_seen: When it last asked for anything, or None.
    """

    device_id: str
    token_hash: str
    name: str
    created_at: float
    last_seen: float | None = None


def hash_token(token: str) -> str:
    """How a device token is stored. One way, on purpose."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


@dataclass
class Session:
    token: str
    started_at: float
    verified_at: float


@dataclass
class AuthStore:
    """The registered passkeys and the sessions they opened.

    Credentials are the one thing here worth keeping across a restart:
    being asked to register a phone again every time the gateway
    reboots would train somebody to click through it. They are public
    keys, so a file is a fine place for them.

    Sessions are not kept. A restart signs everybody out, which is the
    safe direction to fail in.
    """

    path: Path | None = None
    credentials: dict[str, Credential] = field(default_factory=dict)
    devices: dict[str, Device] = field(default_factory=dict)
    _sessions: dict[str, Session] = field(default_factory=dict)
    _challenges: dict[str, tuple[bytes, float]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.load()

    # -- credentials ----------------------------------------------------

    def load(self) -> None:
        if self.path is None or not self.path.is_file():
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        if not isinstance(raw, dict):
            return
        for entry in raw.get("credentials", []):
            if not isinstance(entry, dict):
                continue
            try:
                credential = Credential(
                    credential_id=str(entry["credential_id"]),
                    public_key=str(entry["public_key"]),
                    sign_count=int(entry.get("sign_count", 0)),
                    name=str(entry.get("name", "device")),
                    created_at=float(entry.get("created_at", 0.0)),
                )
            except (KeyError, TypeError, ValueError):
                continue
            self.credentials[credential.credential_id] = credential

        for entry in raw.get("devices", []):
            if not isinstance(entry, dict):
                continue
            try:
                device = Device(
                    device_id=str(entry["device_id"]),
                    token_hash=str(entry["token_hash"]),
                    name=str(entry.get("name", "device")),
                    created_at=float(entry.get("created_at", 0.0)),
                    last_seen=entry.get("last_seen"),
                )
            except (KeyError, TypeError, ValueError):
                continue
            self.devices[device.device_id] = device

    def save(self) -> None:
        if self.path is None:
            return
        payload = {
            "credentials": [
                {
                    "credential_id": c.credential_id,
                    "public_key": c.public_key,
                    "sign_count": c.sign_count,
                    "name": c.name,
                    "created_at": c.created_at,
                }
                for c in self.credentials.values()
            ],
            "devices": [
                {
                    "device_id": d.device_id,
                    "token_hash": d.token_hash,
                    "name": d.name,
                    "created_at": d.created_at,
                    "last_seen": d.last_seen,
                }
                for d in self.devices.values()
            ],
        }
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            tmp.replace(self.path)
        except OSError:
            # A gateway that cannot write its credential file still works
            # for this run. Failing to start would be worse.
            pass

    def add(self, credential: Credential) -> None:
        if len(self.credentials) >= MAX_CREDENTIALS:
            oldest = min(self.credentials.values(), key=lambda c: c.created_at)
            del self.credentials[oldest.credential_id]
        self.credentials[credential.credential_id] = credential
        self.save()

    def revoke(self, credential_id: str) -> bool:
        if credential_id not in self.credentials:
            return False
        del self.credentials[credential_id]
        self.save()
        return True

    @property
    def has_credentials(self) -> bool:
        return bool(self.credentials)

    # -- paired devices -------------------------------------------------

    def pair_device(self, name: str, *, now: float | None = None) -> tuple[Device, str]:
        """Issue a token for a new device. Returns it once, and never again.

        The token is what the glasses will send. Only its hash is kept, so
        somebody who reads this gateway's credential file learns nothing
        they could use.
        """
        moment = time.time() if now is None else now
        if len(self.devices) >= MAX_DEVICES:
            oldest = min(self.devices.values(), key=lambda d: d.created_at)
            del self.devices[oldest.device_id]

        token = secrets.token_urlsafe(32)
        device = Device(
            device_id=secrets.token_hex(8),
            token_hash=hash_token(token),
            name=(name or "Raven Prism")[:40],
            created_at=moment,
        )
        self.devices[device.device_id] = device
        self.save()
        return device, token

    def device_for(self, token: str | None, *, now: float | None = None):
        """The device that token belongs to, or None.

        Compared by hash and in constant time, so a wrong token teaches
        nothing about how wrong it was.
        """
        if not token:
            return None
        wanted = hash_token(token)
        for device in self.devices.values():
            if secrets.compare_digest(device.token_hash, wanted):
                moment = time.time() if now is None else now
                self.devices[device.device_id] = _replace_device(device, moment)
                return self.devices[device.device_id]
        return None

    def revoke_device(self, device_id: str) -> bool:
        if device_id not in self.devices:
            return False
        del self.devices[device_id]
        self.save()
        return True

    def devices_payload(self) -> list[dict]:
        """What Control lists. No token, and nothing derived from one."""
        return [
            {
                "device_id": d.device_id,
                "name": d.name,
                "created_at": d.created_at,
                "last_seen": d.last_seen,
            }
            for d in sorted(self.devices.values(), key=lambda d: d.created_at)
        ]

    # -- challenges -----------------------------------------------------

    def new_challenge(self, purpose: str, challenge: bytes) -> None:
        self._challenges[purpose] = (challenge, time.time())

    def take_challenge(self, purpose: str, *, now: float | None = None) -> bytes | None:
        """One use only. A challenge that is reused is a replay."""
        moment = time.time() if now is None else now
        entry = self._challenges.pop(purpose, None)
        if entry is None:
            return None
        challenge, issued = entry
        if moment - issued > CHALLENGE_SECONDS:
            return None
        return challenge

    # -- sessions -------------------------------------------------------

    def open_session(self, *, now: float | None = None) -> str:
        moment = time.time() if now is None else now
        token = secrets.token_urlsafe(32)
        self._sessions[token] = Session(
            token=token, started_at=moment, verified_at=moment
        )
        return token

    def session(self, token: str | None, *, now: float | None = None):
        """The live session for a token, or None."""
        if not token:
            return None
        moment = time.time() if now is None else now
        found = self._sessions.get(token)
        if found is None:
            return None
        if moment - found.started_at > SESSION_SECONDS:
            del self._sessions[token]
            return None
        return found

    def is_signed_in(self, token: str | None, *, now: float | None = None) -> bool:
        return self.session(token, now=now) is not None

    def is_fresh(self, token: str | None, *, now: float | None = None) -> bool:
        """Whether the passkey was used recently enough for admin work.

        Reading tasks all day on one sign-in is fine. Revoking a device
        should mean touching the sensor again, so that somebody who picks
        up an unlocked phone cannot quietly unpair the glasses.
        """
        found = self.session(token, now=now)
        if found is None:
            return False
        moment = time.time() if now is None else now
        return moment - found.verified_at <= FRESH_SECONDS

    def close_session(self, token: str | None) -> None:
        if token:
            self._sessions.pop(token, None)

    def close_all(self) -> None:
        self._sessions.clear()


def _replace_device(device: Device, seen: float) -> Device:
    from dataclasses import replace as _replace

    return _replace(device, last_seen=seen)


def library_available() -> bool:
    """Whether the WebAuthn library is installed on this gateway."""
    try:
        import webauthn  # noqa: F401
    except ImportError:
        return False
    return True


def _require_library():
    try:
        import webauthn
        from webauthn.helpers import base64url_to_bytes, bytes_to_base64url
        from webauthn.helpers.structs import (
            AuthenticatorSelectionCriteria,
            PublicKeyCredentialDescriptor,
            ResidentKeyRequirement,
            UserVerificationRequirement,
        )
    except ImportError as exc:
        raise AuthUnavailable(
            "Authentication needs the webauthn package. "
            'Install it with: pip install ".[gateway]"'
        ) from exc
    return (
        webauthn,
        base64url_to_bytes,
        bytes_to_base64url,
        AuthenticatorSelectionCriteria,
        PublicKeyCredentialDescriptor,
        ResidentKeyRequirement,
        UserVerificationRequirement,
    )


def registration_options(store: AuthStore, *, rp_id: str, origin: str) -> dict:
    """Start registering a passkey. Returns what the browser needs."""
    (
        webauthn,
        _b64_to_bytes,
        _bytes_to_b64,
        AuthenticatorSelection,
        Descriptor,
        ResidentKey,
        UserVerification,
    ) = _require_library()

    options = webauthn.generate_registration_options(
        rp_id=rp_id,
        rp_name="Agent HUD",
        # A fixed local user. This gateway belongs to one person; there
        # are no accounts here and nothing to enumerate.
        user_id=b"agent-hud-owner",
        user_name="owner",
        user_display_name="Agent HUD",
        authenticator_selection=AuthenticatorSelection(
            resident_key=ResidentKey.PREFERRED,
            user_verification=UserVerification.PREFERRED,
        ),
        exclude_credentials=[
            Descriptor(id=_b64_to_bytes(c.credential_id))
            for c in store.credentials.values()
        ],
    )
    store.new_challenge("register", options.challenge)
    return json.loads(webauthn.options_to_json(options))


def verify_registration(
    store: AuthStore, credential_json: str, *, rp_id: str, origin: str, name: str
) -> Credential:
    """Finish registering. Raises ValueError if it does not check out."""
    webauthn, _b64_to_bytes, bytes_to_b64, *_ = _require_library()

    challenge = store.take_challenge("register")
    if challenge is None:
        raise ValueError("that registration took too long; start again")

    verification = webauthn.verify_registration_response(
        credential=credential_json,
        expected_challenge=challenge,
        expected_rp_id=rp_id,
        expected_origin=origin,
    )

    credential = Credential(
        credential_id=bytes_to_b64(verification.credential_id),
        public_key=bytes_to_b64(verification.credential_public_key),
        sign_count=verification.sign_count,
        name=(name or "device")[:40],
        created_at=time.time(),
    )
    store.add(credential)
    return credential


def authentication_options(store: AuthStore, *, rp_id: str) -> dict:
    """Start signing in."""
    (
        webauthn,
        b64_to_bytes,
        _bytes_to_b64,
        _selection,
        Descriptor,
        _resident,
        UserVerification,
    ) = _require_library()

    options = webauthn.generate_authentication_options(
        rp_id=rp_id,
        allow_credentials=[
            Descriptor(id=b64_to_bytes(c.credential_id))
            for c in store.credentials.values()
        ],
        user_verification=UserVerification.PREFERRED,
    )
    store.new_challenge("login", options.challenge)
    return json.loads(webauthn.options_to_json(options))


def verify_authentication(
    store: AuthStore, credential_json: str, *, rp_id: str, origin: str
) -> str:
    """Finish signing in and open a session. Raises ValueError if not."""
    webauthn, b64_to_bytes, _bytes_to_b64, *_ = _require_library()

    challenge = store.take_challenge("login")
    if challenge is None:
        raise ValueError("that sign-in took too long; start again")

    try:
        parsed = json.loads(credential_json)
        credential_id = str(parsed["id"])
    except (ValueError, KeyError, TypeError) as exc:
        raise ValueError("that sign-in could not be read") from exc

    known = store.credentials.get(credential_id)
    if known is None:
        raise ValueError("that passkey is not registered here")

    verification = webauthn.verify_authentication_response(
        credential=credential_json,
        expected_challenge=challenge,
        expected_rp_id=rp_id,
        expected_origin=origin,
        credential_public_key=b64_to_bytes(known.public_key),
        credential_current_sign_count=known.sign_count,
    )

    # The authenticator's counter only goes up. One that has gone
    # backwards means two things are claiming to be the same key.
    from dataclasses import replace as _replace

    store.credentials[credential_id] = _replace(
        known, sign_count=verification.new_sign_count
    )
    store.save()

    return store.open_session()

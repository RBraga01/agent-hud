"""Tests for who is allowed to talk to the gateway.

The ceremonies themselves are py_webauthn's job, and deliberately so:
verifying a signature means parsing COSE keys and getting a dozen small
things right, and a subtly wrong version of that is worse than none
because it still looks like a lock.

What is tested here is the policy around it. What gets stored, what
cannot get stored, how long a session lasts, what a stale challenge does,
and whether asking twice with the same one works.
"""

import json
import time

import pytest

from stub_server.auth import (
    CHALLENGE_SECONDS,
    FRESH_SECONDS,
    MAX_CREDENTIALS,
    SESSION_SECONDS,
    AuthStore,
    AuthUnavailable,
    Credential,
    library_available,
)

NOW = 1_000_000.0


def credential(n=0, created=NOW):
    return Credential(
        credential_id=f"cred-{n}",
        public_key=f"public-key-{n}",
        sign_count=n,
        name=f"device {n}",
        created_at=created,
    )


@pytest.fixture
def store(tmp_path):
    return AuthStore(path=tmp_path / "passkeys.json")


# --- what is stored, and what cannot be -------------------------------


def test_a_credential_holds_only_public_things():
    """Nothing here could hold a secret even by mistake.

    A passkey works because the private half never leaves the device that
    made it. If a field ever appears here that could hold one -- or a
    password, or anything derived from a fingerprint -- this is the test
    that should stop it.
    """
    fields = set(Credential.__dataclass_fields__)

    assert fields == {
        "credential_id",
        "public_key",
        "sign_count",
        "name",
        "created_at",
    }
    for forbidden in ("password", "secret", "private", "biometric", "template"):
        assert not any(forbidden in name for name in fields)


def test_no_biometric_word_appears_anywhere_in_the_module():
    # The phone's own sensor unlocks the key. This gateway is not told
    # which, is not told whether one was used, and has nowhere to put one.
    import inspect

    from stub_server import auth

    source = inspect.getsource(auth).lower()

    for forbidden in ("fingerprint_data", "face_template", "biometric_template"):
        assert forbidden not in source


def test_a_registered_passkey_is_remembered(store):
    store.add(credential(1))

    assert store.has_credentials is True
    assert "cred-1" in store.credentials


def test_credentials_survive_a_restart(tmp_path):
    # Being asked to register a phone again on every reboot would train
    # somebody to click through it without reading.
    path = tmp_path / "passkeys.json"
    AuthStore(path=path).add(credential(1))

    again = AuthStore(path=path)

    assert "cred-1" in again.credentials
    assert again.credentials["cred-1"].public_key == "public-key-1"


def test_sessions_do_not_survive_a_restart(tmp_path):
    # Signing everybody out is the safe direction to fail in.
    path = tmp_path / "passkeys.json"
    first = AuthStore(path=path)
    first.add(credential(1))
    token = first.open_session(now=NOW)

    again = AuthStore(path=path)

    assert again.is_signed_in(token, now=NOW) is False


def test_a_damaged_credential_file_does_not_stop_the_gateway(tmp_path):
    path = tmp_path / "passkeys.json"
    path.write_text("{ half written", encoding="utf-8")

    store = AuthStore(path=path)

    assert store.credentials == {}


def test_a_credential_entry_that_makes_no_sense_is_skipped(tmp_path):
    path = tmp_path / "passkeys.json"
    path.write_text(
        json.dumps({"credentials": [{"nope": 1}, {"credential_id": "ok",
                    "public_key": "k", "sign_count": 0}]}),
        encoding="utf-8",
    )

    store = AuthStore(path=path)

    assert list(store.credentials) == ["ok"]


def test_revoking_a_passkey_removes_it_for_good(store):
    store.add(credential(1))

    assert store.revoke("cred-1") is True
    assert store.has_credentials is False
    assert AuthStore(path=store.path).credentials == {}


def test_revoking_something_that_is_not_there_changes_nothing(store):
    assert store.revoke("nope") is False


def test_credentials_do_not_pile_up_without_bound(store):
    for n in range(MAX_CREDENTIALS + 5):
        store.add(credential(n, created=NOW + n))

    assert len(store.credentials) <= MAX_CREDENTIALS


def test_a_gateway_that_cannot_write_still_works(tmp_path):
    # Failing to start would be worse than not remembering.
    store = AuthStore(path=tmp_path / "no-such-dir" / "sub" / "x.json")
    store.path = tmp_path  # a directory: writing here will fail

    store.add(credential(1))

    assert "cred-1" in store.credentials


# --- challenges are used once -----------------------------------------


def test_a_challenge_can_only_be_used_once(store):
    # Using one twice is a replay, and the second use must find nothing.
    store.new_challenge("login", b"abc")

    assert store.take_challenge("login", now=NOW) == b"abc"
    assert store.take_challenge("login", now=NOW) is None


def test_a_stale_challenge_is_refused(store):
    store.new_challenge("login", b"abc")
    store._challenges["login"] = (b"abc", NOW - CHALLENGE_SECONDS - 1)

    assert store.take_challenge("login", now=NOW) is None


def test_a_challenge_for_one_purpose_is_not_a_challenge_for_another(store):
    store.new_challenge("register", b"abc")

    assert store.take_challenge("login", now=NOW) is None


# --- sessions ---------------------------------------------------------


def test_signing_in_opens_a_session(store):
    token = store.open_session(now=NOW)

    assert store.is_signed_in(token, now=NOW) is True


def test_no_token_is_not_signed_in(store):
    assert store.is_signed_in(None, now=NOW) is False
    assert store.is_signed_in("", now=NOW) is False
    assert store.is_signed_in("invented", now=NOW) is False


def test_a_session_does_not_last_for_ever(store):
    token = store.open_session(now=NOW)

    assert store.is_signed_in(token, now=NOW + SESSION_SECONDS + 1) is False


def test_two_sessions_are_two_different_tokens(store):
    assert store.open_session(now=NOW) != store.open_session(now=NOW)


def test_signing_out_ends_it(store):
    token = store.open_session(now=NOW)

    store.close_session(token)

    assert store.is_signed_in(token, now=NOW) is False


def test_signing_everybody_out_ends_all_of_them(store):
    a, b = store.open_session(now=NOW), store.open_session(now=NOW)

    store.close_all()

    assert store.is_signed_in(a, now=NOW) is False
    assert store.is_signed_in(b, now=NOW) is False


# --- administration asks again -----------------------------------------


def test_a_fresh_sign_in_may_do_administration(store):
    token = store.open_session(now=NOW)

    assert store.is_fresh(token, now=NOW) is True


def test_reading_all_day_on_one_sign_in_is_fine_but_admin_is_not(store):
    """Somebody who picks up an unlocked phone should not be able to
    quietly unpair the glasses."""
    token = store.open_session(now=NOW)
    later = NOW + FRESH_SECONDS + 1

    assert store.is_signed_in(token, now=later) is True
    assert store.is_fresh(token, now=later) is False


def test_an_expired_session_is_never_fresh(store):
    token = store.open_session(now=NOW)

    assert store.is_fresh(token, now=NOW + SESSION_SECONDS + 1) is False


# --- the library ------------------------------------------------------


def test_the_gateway_can_tell_whether_the_library_is_installed():
    assert library_available() in (True, False)


@pytest.mark.skipif(library_available(), reason="the library is installed")
def test_without_the_library_it_says_so_rather_than_failing_oddly(store):
    from stub_server.auth import registration_options

    with pytest.raises(AuthUnavailable) as raised:
        registration_options(store, rp_id="localhost", origin="http://localhost")

    assert "pip install" in str(raised.value)


@pytest.mark.skipif(not library_available(), reason="needs the webauthn package")
def test_registration_options_are_real_and_carry_a_challenge(store):
    from stub_server.auth import registration_options

    options = registration_options(
        store, rp_id="localhost", origin="http://localhost:8765"
    )

    assert options["rp"]["id"] == "localhost"
    assert options["challenge"]
    assert "login" not in store._challenges
    assert "register" in store._challenges


@pytest.mark.skipif(not library_available(), reason="needs the webauthn package")
def test_a_registered_passkey_is_excluded_from_registering_again(store):
    from webauthn.helpers import bytes_to_base64url

    from stub_server.auth import registration_options

    store.add(
        Credential(
            credential_id=bytes_to_base64url(b"an-existing-key"),
            public_key="k",
            sign_count=0,
            name="phone",
            created_at=NOW,
        )
    )

    options = registration_options(
        store, rp_id="localhost", origin="http://localhost:8765"
    )

    assert len(options["excludeCredentials"]) == 1


@pytest.mark.skipif(not library_available(), reason="needs the webauthn package")
def test_authentication_options_only_offer_registered_passkeys(store):
    from webauthn.helpers import bytes_to_base64url

    from stub_server.auth import authentication_options

    store.add(
        Credential(
            credential_id=bytes_to_base64url(b"a-key"),
            public_key="k",
            sign_count=0,
            name="phone",
            created_at=NOW,
        )
    )

    options = authentication_options(store, rp_id="localhost")

    assert len(options["allowCredentials"]) == 1
    assert options["challenge"]


@pytest.mark.skipif(not library_available(), reason="needs the webauthn package")
def test_a_sign_in_with_a_passkey_we_do_not_know_is_refused(store):
    from stub_server.auth import authentication_options, verify_authentication

    authentication_options(store, rp_id="localhost")

    with pytest.raises(ValueError, match="not registered"):
        verify_authentication(
            store,
            json.dumps({"id": "never-seen-this"}),
            rp_id="localhost",
            origin="http://localhost:8765",
        )


@pytest.mark.skipif(not library_available(), reason="needs the webauthn package")
def test_finishing_a_ceremony_that_was_never_started_is_refused(store):
    from stub_server.auth import verify_authentication

    with pytest.raises(ValueError, match="too long"):
        verify_authentication(
            store,
            json.dumps({"id": "anything"}),
            rp_id="localhost",
            origin="http://localhost:8765",
        )


@pytest.mark.skipif(not library_available(), reason="needs the webauthn package")
def test_a_forged_sign_in_does_not_open_a_session(store):
    """The whole point, end to end.

    A response that was not signed by the registered key must be refused
    by the library, and no session must come out of it.
    """
    from webauthn.helpers import bytes_to_base64url

    from stub_server.auth import authentication_options, verify_authentication

    key_id = bytes_to_base64url(b"a-key")
    store.add(
        Credential(
            credential_id=key_id, public_key=bytes_to_base64url(b"not-a-real-key"),
            sign_count=0, name="phone", created_at=NOW,
        )
    )
    authentication_options(store, rp_id="localhost")

    forged = json.dumps(
        {
            "id": key_id,
            "rawId": key_id,
            "type": "public-key",
            "response": {
                "clientDataJSON": bytes_to_base64url(b"{}"),
                "authenticatorData": bytes_to_base64url(b"\x00" * 37),
                "signature": bytes_to_base64url(b"forged"),
            },
        }
    )

    # The library raises its own type for this; what matters is that it
    # refuses, not which class it refuses with.
    with pytest.raises(Exception):  # noqa: B017
        verify_authentication(
            store, forged, rp_id="localhost", origin="http://localhost:8765"
        )

    assert all(
        not store.is_signed_in(token, now=time.time()) for token in store._sessions
    ) or not store._sessions

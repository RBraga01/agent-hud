"""TLS for a gateway that is reachable off this machine.

Two halves: the gateway resolves a certificate to serve with
(``stub_server.tls``), and the glasses decide how to trust what they are
handed (``agent_hud.tls``).
"""

from __future__ import annotations

import hashlib
import os
import ssl

import pytest

from stub_server.tls import CertInfo, ensure_cert, fingerprint_of, server_context

pytest.importorskip("cryptography")


# --- the self-signed certificate ----------------------------------------


def test_it_makes_a_certificate_and_key_where_it_was_told_to(tmp_path):
    info = ensure_cert(store_dir=tmp_path)

    assert info.certfile == tmp_path / "gateway-cert.pem"
    assert info.keyfile == tmp_path / "gateway-key.pem"
    assert info.certfile.is_file()
    assert info.keyfile.is_file()
    assert info.self_signed is True


def test_the_fingerprint_looks_like_openssl_prints_it(tmp_path):
    info = ensure_cert(store_dir=tmp_path)

    parts = info.fingerprint.split(":")
    assert len(parts) == 32
    assert all(len(p) == 2 for p in parts)
    assert info.fingerprint == info.fingerprint.upper()
    # and it is genuinely the SHA-256 of the DER certificate
    from cryptography import x509
    from cryptography.hazmat.primitives.serialization import Encoding

    cert = x509.load_pem_x509_certificate(info.certfile.read_bytes())
    want = hashlib.sha256(cert.public_bytes(Encoding.DER)).hexdigest().upper()
    assert info.fingerprint.replace(":", "") == want


def test_it_is_generated_once_and_then_reused(tmp_path):
    first = ensure_cert(store_dir=tmp_path)
    stamp = first.certfile.stat().st_mtime_ns
    body = first.certfile.read_bytes()

    second = ensure_cert(store_dir=tmp_path)

    assert second.fingerprint == first.fingerprint
    assert second.certfile.read_bytes() == body
    assert second.certfile.stat().st_mtime_ns == stamp


def test_the_certificate_covers_localhost_and_the_bind_address(tmp_path):
    from cryptography import x509

    info = ensure_cert(store_dir=tmp_path, hosts=["10.0.0.5"])
    cert = x509.load_pem_x509_certificate(info.certfile.read_bytes())
    san = cert.extensions.get_extension_for_class(
        x509.SubjectAlternativeName
    ).value

    names = set(san.get_values_for_type(x509.DNSName))
    addrs = {str(ip) for ip in san.get_values_for_type(x509.IPAddress)}
    assert "localhost" in names
    assert "127.0.0.1" in addrs
    assert "10.0.0.5" in addrs


@pytest.mark.skipif(os.name == "nt", reason="POSIX file modes only")
def test_the_private_key_is_not_world_readable(tmp_path):
    info = ensure_cert(store_dir=tmp_path)
    mode = info.keyfile.stat().st_mode & 0o077
    assert mode == 0


# --- bring your own ----------------------------------------------------


def test_a_certificate_you_supply_is_used_as_is(tmp_path):
    made = ensure_cert(store_dir=tmp_path / "made")

    info = ensure_cert(
        cert_path=made.certfile,
        key_path=made.keyfile,
        store_dir=tmp_path / "unused",
    )

    assert info.certfile == made.certfile
    assert info.keyfile == made.keyfile
    assert info.self_signed is False
    assert info.fingerprint == made.fingerprint
    assert not (tmp_path / "unused").exists()


def test_a_missing_supplied_certificate_is_an_error_not_a_silent_self_sign(tmp_path):
    with pytest.raises(FileNotFoundError):
        ensure_cert(
            cert_path=tmp_path / "nope.pem",
            key_path=tmp_path / "nope-key.pem",
            store_dir=tmp_path,
        )


# --- the server context ----------------------------------------------------


def test_the_server_context_will_not_speak_anything_older_than_tls_1_2(tmp_path):
    info = ensure_cert(store_dir=tmp_path)
    ctx = server_context(info)

    assert isinstance(ctx, ssl.SSLContext)
    assert ctx.minimum_version >= ssl.TLSVersion.TLSv1_2


def test_fingerprint_of_matches_the_info_it_was_read_from(tmp_path):
    info = ensure_cert(store_dir=tmp_path)
    assert fingerprint_of(info.certfile) == info.fingerprint


def test_cert_info_is_frozen(tmp_path):
    import dataclasses

    info = ensure_cert(store_dir=tmp_path)
    assert isinstance(info, CertInfo)
    with pytest.raises(dataclasses.FrozenInstanceError):
        info.fingerprint = "x"  # type: ignore[misc]


# --- how the glasses decide to trust ----------------------------------


def test_plain_session_verifies_the_ordinary_way():
    from agent_hud.tls import session_for

    session = session_for()
    assert session.verify is True


def test_a_ca_file_becomes_the_thing_to_verify_against():
    from agent_hud.tls import session_for

    session = session_for(ca="/etc/agent-hud/private-ca.pem")
    assert session.verify == "/etc/agent-hud/private-ca.pem"


def test_a_fingerprint_mounts_a_pinning_adapter_for_https():
    from agent_hud.tls import session_for

    session = session_for(fingerprint="AA:BB:CC")
    adapter = session.get_adapter("https://anything.example")
    assert type(adapter).__name__ == "_PinnedAdapter"


def test_a_fingerprint_wins_over_a_ca():
    from agent_hud.tls import session_for

    session = session_for(fingerprint="AA:BB", ca="/some/ca.pem")
    assert type(session.get_adapter("https://x")).__name__ == "_PinnedAdapter"


def test_the_pinned_adapter_tells_the_connection_to_check_the_fingerprint():
    import ssl as _ssl
    import types

    from agent_hud.tls import _pinned_adapter

    adapter = _pinned_adapter("Aa:Bb Cc")
    conn = types.SimpleNamespace()
    adapter.cert_verify(conn, "https://gw.example/x", verify=True, cert=None)

    assert conn.assert_fingerprint == "aabbcc"  # colons, spaces, case gone
    assert conn.assert_hostname is False
    assert conn.cert_reqs == _ssl.CERT_NONE
    assert conn.ca_certs is None

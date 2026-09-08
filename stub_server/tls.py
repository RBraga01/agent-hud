"""TLS for a gateway that is reachable off this machine.

Two ways to get a certificate:

* **Bring your own.** Point ``AGENT_HUD_TLS_CERT`` and ``AGENT_HUD_TLS_KEY``
  at a real certificate -- from a domain you own, Caddy, a Tailscale
  cert, mkcert. The glasses then verify it the ordinary way, against the
  system trust store or a CA file.

* **Self-signed, pinned.** With no certificate configured, the gateway
  makes one, keeps it at ``~/.agent-hud/gateway-cert.pem`` (and its key
  beside it), and prints its SHA-256 fingerprint. The glasses trust
  *that one certificate* by pinning the fingerprint --
  ``AGENT_HUD_GATEWAY_FINGERPRINT`` -- which is the right amount of trust
  for a box on your own network where there is no CA in the picture.

The self-signed certificate is generated once and reused. Regenerating it
on every start would change the fingerprint and break every pinned
client, so it is written to disk and loaded back.
"""

from __future__ import annotations

import contextlib
import datetime
import hashlib
import ssl
from dataclasses import dataclass
from pathlib import Path

_CERT_NAME = "gateway-cert.pem"
_KEY_NAME = "gateway-key.pem"

# Long, because a pinned certificate is trusted by its fingerprint, not by
# a validity window a CA vouches for. Still finite, so a forgotten box
# eventually stops answering rather than never.
_SELF_SIGNED_DAYS = 3650


@dataclass(frozen=True)
class CertInfo:
    certfile: Path
    keyfile: Path
    fingerprint: str
    self_signed: bool


def fingerprint_of(certfile: Path) -> str:
    """The certificate's SHA-256 fingerprint, ``AA:BB:CC:...``.

    The same string ``openssl x509 -fingerprint -sha256`` prints, and what
    a pinning client compares against.
    """
    from cryptography import x509

    cert = x509.load_pem_x509_certificate(Path(certfile).read_bytes())
    digest = hashlib.sha256(cert.public_bytes(_der())).hexdigest().upper()
    return ":".join(digest[i : i + 2] for i in range(0, len(digest), 2))


def _der():
    from cryptography.hazmat.primitives.serialization import Encoding

    return Encoding.DER


def _generate(certfile: Path, keyfile: Path, hosts: list[str]) -> None:
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID

    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name(
        [x509.NameAttribute(NameOID.COMMON_NAME, "Agent HUD gateway")]
    )

    sans: list[x509.GeneralName] = []
    seen: set[str] = set()
    for host in [*hosts, "localhost", "127.0.0.1", "::1"]:
        host = (host or "").strip()
        if not host or host in seen:
            continue
        seen.add(host)
        try:
            import ipaddress

            sans.append(x509.IPAddress(ipaddress.ip_address(host)))
        except ValueError:
            sans.append(x509.DNSName(host))

    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(minutes=5))
        .not_valid_after(now + datetime.timedelta(days=_SELF_SIGNED_DAYS))
        .add_extension(x509.SubjectAlternativeName(sans), critical=False)
        .add_extension(
            x509.BasicConstraints(ca=False, path_length=None), critical=True
        )
        .sign(key, hashes.SHA256())
    )

    certfile.parent.mkdir(parents=True, exist_ok=True)
    keyfile.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    with contextlib.suppress(OSError):
        keyfile.chmod(0o600)
    certfile.write_bytes(cert.public_bytes(serialization.Encoding.PEM))


def ensure_cert(
    *,
    cert_path: Path | str | None = None,
    key_path: Path | str | None = None,
    store_dir: Path | str,
    hosts: list[str] | None = None,
) -> CertInfo:
    """Resolve a certificate to serve with.

    When ``cert_path`` and ``key_path`` are both given they are used as
    is. Otherwise a self-signed pair in ``store_dir`` is loaded, or made
    once and then loaded.
    """
    if cert_path and key_path:
        cert, key = Path(cert_path), Path(key_path)
        if not cert.is_file() or not key.is_file():
            raise FileNotFoundError(
                f"TLS cert or key not found: {cert}, {key}"
            )
        return CertInfo(cert, key, fingerprint_of(cert), self_signed=False)

    store = Path(store_dir)
    cert, key = store / _CERT_NAME, store / _KEY_NAME
    if not (cert.is_file() and key.is_file()):
        _generate(cert, key, list(hosts or []))
    return CertInfo(cert, key, fingerprint_of(cert), self_signed=True)


def server_context(info: CertInfo) -> ssl.SSLContext:
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(certfile=str(info.certfile), keyfile=str(info.keyfile))
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    return ctx


__all__ = ["CertInfo", "ensure_cert", "fingerprint_of", "server_context"]

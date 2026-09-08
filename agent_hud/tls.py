"""How the glasses decide to trust the gateway they are talking to.

Three cases:

* **Plain http, or a publicly-trusted certificate.** Nothing to
  configure. ``requests`` verifies against the system trust store.
* **Bring-your-own certificate.** ``AGENT_HUD_GATEWAY_CA`` points at the
  certificate (or CA) file to trust for this gateway.
* **Self-signed, pinned.** ``AGENT_HUD_GATEWAY_FINGERPRINT`` holds the
  gateway's SHA-256 fingerprint. The connection is accepted only if the
  certificate presented hashes to exactly that -- name and CA are not
  checked, because with a self-signed cert there is nothing to check them
  against.
"""

from __future__ import annotations

import ssl

import requests
from requests.adapters import HTTPAdapter


def _pinned_adapter(fingerprint: str) -> HTTPAdapter:
    wanted = fingerprint.replace(":", "").replace(" ", "").lower()

    class _PinnedAdapter(HTTPAdapter):
        """Trust exactly one certificate, by its fingerprint.

        ``requests`` sets up CA verification on the connection in
        ``cert_verify`` -- run for every request, after the pool is
        chosen. Replacing it is the one reliable point across
        ``requests`` versions to say instead: do not check a CA chain or
        a hostname, check that the certificate is *this* one. urllib3
        does the SHA-256 comparison itself once the handshake completes.
        """

        def cert_verify(self, conn, url, verify, cert):
            conn.cert_reqs = ssl.CERT_NONE
            conn.ca_certs = None
            conn.ca_cert_dir = None
            conn.ca_cert_data = None
            conn.assert_hostname = False
            conn.assert_fingerprint = wanted

    return _PinnedAdapter()


def session_for(*, fingerprint: str = "", ca: str = "") -> requests.Session:
    """A ``requests`` session that trusts this gateway the configured way.

    ``fingerprint`` wins if both are set: a pin is the most specific
    statement of trust.
    """
    session = requests.Session()
    if fingerprint.strip():
        session.mount("https://", _pinned_adapter(fingerprint.strip()))
        return session
    if ca.strip():
        session.verify = ca.strip()
    return session


__all__ = ["session_for"]

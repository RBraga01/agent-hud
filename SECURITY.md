# Security Policy

## Reporting a problem

If you find a security problem in agent-hud, please report it privately.

**Do not open a public issue for a security problem.**

Use [GitHub's private vulnerability reporting](https://github.com/RBraga01/agent-hud/security/advisories/new), or email the repository owner.

Please include what the problem is, how to reproduce it, what it could lead to, and a suggested fix if you have one. You will get a reply within 5 working days.

## What this project is

A display app for smart glasses, plus a small development server. It stores nothing, has no accounts, and has no users other than the person wearing the glasses. The realistic concerns are narrow, and listed below.

## Where the risk actually is

**The gateway is unlocked by default, and that is only safe on loopback.** With `AGENT_HUD_REQUIRE_AUTH` off it serves whatever is in `stub_server/agents.json` to anyone who can reach it, so the default bind is `127.0.0.1` and nothing else. Do not tunnel that default binding anywhere, and do not run it unlocked on a shared machine with anything private in that file.

**Off loopback it insists on more.** `AGENT_HUD_HOST` binds it to a network address, and the gateway refuses to start unless authentication is on (passkeys via `py_webauthn`, with paired-device tokens for the glasses) and it has a TLS certificate — self-signed with a pinned fingerprint, or one you supply. Writes are rate limited per client and the server caps concurrent requests and slow bodies. This makes a network deployment defensible; it does not make the gateway a hardened multi-tenant service. It is still one process holding the credentials for everything it reports on, and it is the thing worth protecting.

**Registering the first passkey is a race, on a network, until one exists.** There has to be an unauthenticated way to set the first passkey or the first paired device up; on loopback that is free, because nothing off the machine can reach it. Exposed, whoever gets there first — you or an attacker who found the address first — wins. So while none exists, the gateway also prints a one-time setup token to its console and requires it for that one window. Open Control and finish registering a passkey as soon as the gateway is reachable from anywhere but your own machine.

**A passkey's origin is decided by the gateway's own TLS, not by a header.** `X-Forwarded-Proto` is ignored unless you explicitly set `AGENT_HUD_TRUST_PROXY_HEADERS=1`, which you should only do when a reverse proxy you control is genuinely terminating TLS in front of the gateway — otherwise a client talking to it directly could claim a scheme it never used.

**The app trusts its gateway's text.** `title` and `detail` are drawn as-is. A gateway that reports attacker-controlled text puts that text in front of the wearer. The parser rejects anything that is not a plain string, so it cannot become code, but it can still mislead. Treat a gateway as trusted infrastructure.

**Settings come from the environment.** No address, key or token is written into the source, and `.env` is ignored by git. If you add a setting, keep it that way.

## The framework is proprietary

The Raven Framework is separate software under a proprietary licence that grants no right to use, modify or redistribute it. It is never installed by automated checks and never committed here.

If you find any part of it in this repository, that is a licence problem rather than a security one — please report it the same private way, and it will be removed.

## Deliberately absent

- No telemetry. The app talks to the gateway you configure and nothing else.
- No stored data. Nothing is written to disk except the log file the framework itself creates, which is ignored by git.
- No credentials in the app. Deployment credentials, when there are any, are
  read from the environment (`RAVEN_APP_ID`, `RAVEN_APP_KEY`) and never written
  into tracked source.

## Supported versions

| Version | Supported |
|---------|-----------|
| Unreleased | Yes |

This is a prototype, validated in the simulator only. Deployment to Prism
hardware needs Raven-issued credentials and a device.

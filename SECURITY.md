# Security Policy

## Reporting a problem

If you find a security problem in agent-hud, please report it privately.

**Do not open a public issue for a security problem.**

Use [GitHub's private vulnerability reporting](https://github.com/RBraga01/agent-hud/security/advisories/new), or email the repository owner.

Please include what the problem is, how to reproduce it, what it could lead to, and a suggested fix if you have one. You will get a reply within 5 working days.

## What this project is

A display app for smart glasses, plus a small development server. It stores nothing, has no accounts, and has no users other than the person wearing the glasses. The realistic concerns are narrow, and listed below.

## Where the risk actually is

**The stub gateway has no authentication of any kind.** It serves whatever is in `stub_server/agents.json` to anyone who asks. It binds to `127.0.0.1` on purpose, so it is reachable only from the machine it runs on. Do not change that binding, do not expose it through a tunnel, and do not run it on a shared machine with anything private in that file. It is a development tool, not a server.

**A real gateway will be a different matter.** This project does not include one. When you build one, it will hold credentials for the services it reports on, and it becomes the thing worth protecting. Nothing in this repository will protect it for you.

**The app trusts its gateway's text.** `title` and `detail` are drawn as-is. A gateway that reports attacker-controlled text puts that text in front of the wearer. The parser rejects anything that is not a plain string, so it cannot become code, but it can still mislead. Treat a gateway as trusted infrastructure.

**Settings come from the environment.** No address, key or token is written into the source, and `.env` is ignored by git. If you add a setting, keep it that way.

## The framework is proprietary

The Raven Framework is separate software under a proprietary licence that grants no right to use, modify or redistribute it. It is never installed by automated checks and never committed here.

If you find any part of it in this repository, that is a licence problem rather than a security one — please report it the same private way, and it will be removed.

## Deliberately absent

- No telemetry. The app talks to the gateway you configure and nothing else.
- No stored data. Nothing is written to disk except the log file the framework itself creates, which is ignored by git.
- No credentials in the app. It has none, and does not need any.

## Supported versions

| Version | Supported |
|---------|-----------|
| Unreleased | Yes |

This is a prototype and cannot yet be deployed to real glasses.

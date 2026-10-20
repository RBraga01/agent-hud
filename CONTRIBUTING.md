# Contributing to agent-hud

## Before you start

Two things about this project are not negotiable, because both protect someone other than you.

**The Raven Framework never enters this repository.** It is proprietary. Its licence states that viewing the source grants no right to use, modify or redistribute it. It is listed in `.gitignore`. Do not add any part of it, do not paste its code into an issue, and do not include it in a pull request.

**Vendor SDKs and packages stay out too.** Halo and MemoMind use pinned public
SDK checkouts in their ignored `vendor/` directories. Do not commit either SDK,
MemoMind's copied Web runtime, or generated `.gmp`/`.mmpkg` packages.

**No credentials, ever.** No API keys, no `app_id`, no `app_key`, no machine names, no internal addresses. Settings come from the environment. `.env` is ignored and must stay that way.

**Invent your test data.** Fixtures must never contain anything seen on a real machine — no real project names, folder layouts, prompts or session identifiers. The feeders read personal files, so it is easy to copy plausible-looking values straight out of a debugging session and into a test. Make them up, and make them obviously made up.

## The test

Before proposing a feature, ask:

> **Does this belong on the glasses, or on the gateway?**

The app draws a list of items. It knows nothing about GitHub, Codex, or any other tool, and it must stay that way — every tool-specific detail belongs on the gateway. This is not tidiness. Changing the glasses app will one day require Raven's approval to publish; changing the gateway will not.

If your feature means teaching the app about a particular service, it belongs on the other side of the connection.

## What good work looks like

**Logic goes in a module that does not need a vendor runtime.** Raven keeps it
in plain Python, Halo in separable Lua modules, and MemoMind keeps codecs and
round-trip policy outside its SDK entry points. Vendor-facing files bind
rendering, input and transport; they do not redefine the shared contract.

**Tests come first, and you watch them fail.** A test you have never seen fail is not a test. It is decoration.

**The app never crashes on bad input.** A malformed item is dropped, not raised. A dead gateway leaves the last known list on screen. An exception on the glasses means a blank display, and a blank display is indistinguishable from "nothing needs you" — the one thing this must never get wrong.

**You ran it.** A passing suite is not evidence the application works. Launch the simulator and look at it. Several real bugs in this project were invisible to a green test run.

## Checks

```bash
pytest
ruff check .
```

Platform-specific checks are documented in each platform README. MemoMind
changes must also pass its native C/JavaScript tests, official SDK build,
MMPKG packaging and pair metadata check.

Coverage must stay at or above 80 percent on the modules that do not need the framework. Screen tests skip without it, which is expected.

## Design changes

Take values from the framework theme rather than inventing them. Setting a flat border colour switches off Raven's white-to-silver gradient and makes the app look subtly wrong beside a real Raven screen.

If you change anything visual, render it and look at it in all three lighting previews. Daylight is the hard case. `AGENTS.md` lists what this display can and cannot do, and why.

## What not to contribute

- Sending from focus, navigation or action selection. Only a visually distinct
  confirmation state may transmit a decision, with the current revision and a
  stable decision ID.
- Third-party Python packages for the glasses app. How extra packages get installed onto the device is undocumented, so the app uses only what the framework already bundles.
- Anything that assumes a dark background exists. On this display it does not.

## Reporting problems

Open an issue with what you expected, what happened, and which lighting preview you were in if it is visual. For anything security-related see [SECURITY.md](SECURITY.md) instead — do not open a public issue.

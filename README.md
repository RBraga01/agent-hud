# agent-hud

A quiet display for [Raven Prism](https://raven.computer) smart glasses that tells you when something needs your attention.

You run coding agents and jobs on other machines. Today you find out how they are doing by going to a screen and looking. This tells you instead, in the corner of your vision, without you asking.

Most of the time it shows almost nothing. When something is waiting on you, a small number appears. Look at it and it opens to tell you what.

> **Not affiliated with Raven Resonance.** This is an independent project. The Raven Framework is separate proprietary software, installed by hand, and is never included here.

## How it looks

Four states, in daylight and at night:

| State | What is on screen |
|---|---|
| Nothing waiting | One small bright dot in the right periphery. Nothing else. |
| Something waiting | A card holding a number, and the words "need you" |
| Opened | Each item in its own row, with a line counting what did not fit |
| Cannot reach the gateway | The last known count stays, with an amber dot below it |

## What you need

- **Python 3.10 or later** for development. Deploying to real glasses needs exactly **3.12.12** — the Raven tooling checks the version string and refuses anything else.
- **Git**
- **The Raven Framework**, cloned and installed separately (see below)

## Setup

**1. Get this project**

```bash
git clone https://github.com/RBraga01/agent-hud
cd agent-hud
python -m venv .venv
```

Activate it: `source .venv/bin/activate` on macOS and Linux, `.venv\Scripts\activate` on Windows. If PowerShell blocks that, call the interpreter by path instead: `.venv\Scripts\python.exe`.

**2. Get the Raven Framework**

It is not a dependency of this project and is never bundled with it. Clone it inside this folder, where it is already ignored by git:

```bash
git clone https://github.com/RavenResonance/raven-framework
pip install -e ./raven-framework
```

**3. Install the development tools**

```bash
pip install -e ".[dev]"
```

## Running it

Start the stub gateway in one terminal:

```bash
python -m stub_server.server
```

And the app in another:

```bash
python main.py
```

The simulator opens. Your mouse stands in for where you are looking, a click stands in for the stare or blink that selects something, and the buttons along the bottom preview how it looks in daylight, at night and outdoors. Black shows as transparent, because the real display can only add light to the world — it can never darken it.

Now edit `stub_server/agents.json` and watch the glasses follow within a few seconds.

## Settings

Both are optional and read from the environment. Nothing is written into the source.

| Variable | Default | What it does |
|---|---|---|
| `AGENT_HUD_GATEWAY_URL` | `http://127.0.0.1:8765/items` | Where to ask for the list |
| `AGENT_HUD_POLL_SECONDS` | `3` | How often to ask |

Copy `.env.example` if you want a starting point. A bad value stops the app at startup with a clear message rather than leaving you with a display that quietly does nothing.

## What the gateway sends

The app knows nothing about Codex, GitHub, or any other tool. It receives a list of items and draws them. Everything tool-specific belongs on the server side, so adding a new source never means changing and redeploying the glasses app.

```json
{
  "items": [
    {
      "id": "claude-deploy",
      "title": "Claude Code",
      "detail": "approve deploy?",
      "needs_you": true
    }
  ]
}
```

Four fields, nothing else. `title` and `detail` are already-written text — the app draws them, it never composes sentences. The number in the corner is how many items have `needs_you` set.

Parsing is strict. An entry that does not match this shape exactly is dropped rather than guessed at, because guessing would either hide work from you or invent work that is not there.

## Layout

```
main.py                 entry point
agent_hud/
  config.py             settings from the environment      no framework needed
  items.py              the contract and its parser        no framework needed
  client.py             fetching from the gateway          no framework needed
  interaction.py        when the detail is showing         no framework needed
  app.py                the screen                         needs the framework
stub_server/
  server.py             serves agents.json over HTTP       no framework needed
  agents.json           edit this while testing
tests/
```

Everything that can be plain Python is plain Python. The Raven Framework is proprietary and its licence grants no right to use it, so it is never installed in automated checks — which is why the screen tests skip there and everything else does not.

## Tests

```bash
pytest              # add -q for less noise
ruff check .
```

With the framework installed you get the full suite. Without it, the screen tests skip and the rest still run — the same thing the automated checks see.

## Deploying to glasses

Not possible yet. It needs an app ID and key that Raven issues, and their upload service to be open. Neither is available. When it is:

```bash
python main.py deploy
```

## Licence

MIT — see [LICENSE](LICENSE).

That covers this project's own code. The [Raven Framework](https://github.com/RavenResonance/raven-framework) is separate proprietary software with its own licence, installed by hand, and no part of it appears in this repository. Do not copy it here.

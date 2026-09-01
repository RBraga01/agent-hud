# Changelog

## Unreleased

First working version. Validated in Raven's simulator, not on physical Prism
hardware. The Raven Framework supports deployment; doing so needs Raven-issued
application credentials and a device, neither of which this project has yet.

### Added
- Reads a list of items from a gateway and shows how many need attention.
- A count in the right periphery. Stare at it and the detail opens; look away
  and stay away and it closes.
- Keeps the last known list when the gateway cannot be reached, with a
  separate marker, so an empty display and a broken one never look alike.
- A stub gateway that serves a file you can hand-edit while testing.
- Screen composed from the Raven Framework's own card and button components,
  using the theme's values rather than invented ones.
- Feeders, which are the parts that know about particular tools. The app
  knows about none of them. Invented data by default, so it runs with no
  accounts; a reader for live Claude Code sessions; and a file reader for
  driving the display by hand.
- The gateway asks its feeders on every request, so nothing is ever stale.
- `codex` feeder — recent Codex CLI sessions from `~/.codex`, using the
  session index for titles and the session log's tail for whose turn it
  is. Reads event types only, never message bodies. `feeders/codex.py` is
  the template for other agent CLIs (Cursor, OpenCode, Copilot).
- `claude_hook` feeder plus four Claude Code hooks (`UserPromptSubmit`,
  `Stop`, `StopFailure`, `SessionEnd`) in `integrations/claude_code/`. This
  is the supported way to tell whose turn it is; the transcript-parsing
  `claude` feeder stays as a no-setup fallback. It distinguishes your turn
  from a failure from Claude still doing background work, applies no settle
  delay, cleans up when a session ends, and never reads prompt text or
  error contents.

### Fixed
- A gateway answering with something that is not a list of items was
  reported as "nothing needs you". It is now a failure, and the last known
  list stays on screen with the incomplete marker. This was the single
  worst thing the app could do and it is the reason the parser now reports
  validity separately.
- Entries that fail the contract are counted rather than silently dropped,
  so a list with holes in it is marked incomplete instead of passing as
  whole.
- A slow gateway could leave several requests in flight at once, letting an
  older answer land after a newer one. Only one runs at a time now.
- Project names no longer assume one person's folder layout.
- Long transcripts are read from the end rather than in full, so polling
  does not grow more expensive as sessions get longer.

### Known limits
- Staring can only be tested with a mouse. Real eye tracking is accurate to
  two or three degrees, so the target may need to be larger than it looks.
- Text washes out over a bright sky. The display can only add light, and text
  is already at full white, so there is no headroom left.
- Voice is not built yet. It needs its own design first.
- Not run on real hardware. Eye-tracking accuracy, blink detection and the
  physical button are all unverified.
- Raven's public developer token and its runtime mechanism have not been
  released yet; current internal testing adds credentials locally. This app
  keeps them out of source control and reads them from the environment,
  which is untested on a device.
- The gateway is a loopback-only development server with no authentication.
  A network-reachable gateway is a separate build.
- The `claude` feeder still depends on an undocumented transcript format.
  It is now a fallback — `claude_hook` is the supported path.

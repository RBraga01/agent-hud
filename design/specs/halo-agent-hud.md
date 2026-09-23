# Halo Agent HUD integration specification

## Purpose

Bring the existing Halo emulator implementation into Agent HUD as a first-class
platform without making Raven the default shape of every device. The common
contract defines what a safe decision means. Halo owns how that decision is
shown, navigated and carried over Bluetooth.

Evidence in this milestone is limited to the public Brilliant SDK and Halo
emulator. The repository must not claim physical-device validation.

## Layout

The Halo canvas is 256 by 256 pixels. Content uses a 20-pixel left inset, a
24-pixel top inset and a quiet black canvas. Headings sit at the top, the active
content occupies the middle, and short input guidance sits near the bottom.

```text
Quiet / attention                 Request and choices
┌────────────────────────┐        ┌────────────────────────┐
│                    ○   │        │ HEADING                │
│                        │        │                        │
│                        │        │ Content or choices     │
│                        │        │ inside 216 px width    │
│                        │        │                        │
│                        │        │ INPUT GUIDANCE         │
└────────────────────────┘        └────────────────────────┘
```

- Quiet is a blank canvas. Attention is only a small cyan ring in the top-right.
- Reading screens use no large filled panel; text remains sparse and left aligned.
- A focused menu row uses a dark cyan fill. Meaning is also conveyed by position
  and text, never colour alone.
- Confirmation, delivery uncertainty and stale states use a thin outline around
  the decision information. Success uses an outlined circle plus the word `SENT`.
- Text is capped and wrapped before it can collide with the footer. At most three
  context lines are shown on the request screen.
- This is a fixed square display. There is no narrower responsive breakpoint.
  Longer source text is shortened with `...`; additional actions are rejected at
  the contract boundary rather than drawn off-screen.

## States

| State | Visual treatment | Final copy |
|---|---|---|
| Quiet | Black canvas, no content | No copy |
| Attention | Small cyan ring and centre point | No copy |
| Request | Cyan heading, title, up to three context lines | `REQUEST`, `DOUBLE: ACTIONS` |
| Action menu | Cyan heading, one highlighted row, explicit cancel row | `CHOOSE ACTION`, `Cancel`, profile-specific movement guidance |
| Confirmation | Amber heading and outlined decision card | `CONFIRM`, `VERSION <n>`, `DOUBLE TO SEND` |
| Sending | Amber heading | `SENDING...`, `WAITING FOR RESULT` |
| Sent | Green ring, acknowledgement and chosen action | `SENT`, `OK`, `LONG: CLOSE` |
| Delivery unknown | Red heading and outline | `DELIVERY UNKNOWN`, `CHECK / RETRY`, `RECONFIRM TO RETRY`, `2X REVIEW`, `HOLD CLOSE` |
| Stale | Red heading and outline | `STALE REQUEST`, `RELOAD REQUIRED`, `NOT ACCEPTED`, `2X RELOAD`, `HOLD CLOSE` |
| Rejected | Red heading | `ACTION REJECTED`, `NO LONGER OFFERED`, `LONG: CLOSE` |

The complete AI-state mapping, including states that are deliberately not
streamed on this device, is in `design/ai-states/halo-agent-hud.md`.

## Interactions

Profile B is the documented default for future physical testing because moving
focus and activating a choice use different physical inputs. Profile A remains
available as the one-button baseline.

| Input | Profile A | Profile B | Consequence |
|---|---|---|---|
| Single button click | Move focus | Open request/menu | Never sends |
| Single tap | No action | Move focus | Never sends |
| Double button click | Open/select/confirm | Select/confirm | Sends only from confirmation |
| Long button press | Back/close | Back/close | Never sends |

The journey is `attention -> request -> choices -> confirmation -> sending`.
Choosing an action only opens confirmation. A decision is emitted once, only
after the next deliberate activation. A matching accepted result shows `SENT`.
Unknown delivery returns to review before retry. A newer revision blocks the
decision and requires reload. Cancel and back never emit a decision.

## Edge cases

- Missing or malformed requests leave the display quiet and emit nothing.
- A request from another session is ignored after the first session is locked.
- A newer revision received before confirmation opens the stale state and emits
  nothing.
- A second confirmation while sending cannot emit a duplicate decision.
- Retry reuses the frozen decision identifier.
- Long labels, titles and context are shortened before drawing.
- An unsupported or removed action shows rejection; it is never invented by the
  device.
- Disconnects and unknown results cannot look like success or quiet.

## Repository boundary

- Common schemas, vectors, gateway and feeders stay at repository root.
- Halo Lua, host framing, emulator tests and evidence live under
  `platforms/halo/`.
- Raven remains under `platforms/raven/`; neither runtime imports the other.
- The Brilliant SDK remains a pinned, ignored local dependency. No SDK source,
  private history, cache, binary or local path enters the repository.

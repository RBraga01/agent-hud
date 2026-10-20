# MemoMind Agent HUD renderer specification

## Purpose

Replace the provisional single-label MemoMind screen with a native 600 by 350
HUD composition that belongs to the same product as the Raven and Halo Agent
HUD implementations. MemoMind keeps its own tap and head-motion interaction
model, while preserving the shared safety contract.

The behavioral implementation and phone bridge are not redesigned here. This
specification only changes how the existing states are expressed on the
glasses. A functional round trip is not sufficient for approval: the simulator
must also render the hierarchy and state distinctions described below.

## Visual direction

The renderer uses the existing MemoMind 600 by 350 design mocks as its visual
authority and adapts the Raven outline language to MemoMind's monochrome HUD.

- The canvas is black and unfilled by default.
- Bright green is used for primary outlines and text; softer green is used for
  secondary copy. State meaning never depends on colour.
- Information hierarchy comes from geometry, line weight, spacing and copy.
- Reading states are sparse and left aligned. They are not a centred block of
  newline-separated text.
- Focused controls use a 4-pixel outer border, a 1-pixel inset border and a
  restrained dark fill. Unfocused controls use a 2-pixel border and no fill.
- Confirmation uses a persistent double frame around the whole state, making it
  impossible to confuse with navigation or action selection.
- The renderer uses native LVGL objects: containers, labels and authored line
  geometry. Unicode symbols and emoji are not used as icons.

## Canvas and geometry

The layout is fixed at 600 by 350 logical pixels until the SDK proves another
drawable area. The 600 by 350 canvas is not silently normalised to the reported
physical panel size.

| Token | Value |
|---|---:|
| Safe inset | 28 px |
| Main width | 544 px |
| State heading top | 34 px |
| Main title top | 76 px |
| Body top | 132 px |
| Footer baseline | 326 px |
| Control radius | 10 px |
| Panel radius | 16 px |
| Standard border | 2 px |
| Focus / confirmation border | 4 px |
| Primary control height | 68-78 px |

Only two SDK-owned fonts are currently available. The large font is used for
the main title and primary action. The default font is used for state headings,
context, identity, status and footer guidance. Text is wrapped or clipped
inside its allotted object; it must never overlap another region.

## States and final copy

### Quiet

The canvas is entirely blank while connected and there is no pending request.
When disconnected, a compact `OFFLINE` marker appears in the top-right so a
broken link cannot be mistaken for a healthy quiet state. It must not expand
into a full-screen error card.

### Attention

A compact outlined indicator appears in the top-right. It contains the count
`1` and the label `REQUEST`. No card or explanatory paragraph is shown.

### Request

The request screen uses the full safe width without a surrounding card:

```text
NEEDS YOU · 1 OF 1

<request title>
<short context, maximum three lines>

┌────────────────────────────────────────────────────┐
│  Open request                                      │
└────────────────────────────────────────────────────┘
                              opening sends nothing
```

The open control is focused. Profile A says `TAP: OPEN`; profile B says
`DOUBLE: OPEN`. Opening sends no decision.

### Action menu

The state heading is `CHOOSE AN ACTION`. The screen contains only actions from
the request plus the intrinsic `Back` control. MemoMind uses a two-column grid,
not Raven's gaze-oriented radial menu. With two actions, the actions occupy the
top row and `Back` occupies the lower-left cell. With one action, the action and
`Back` occupy the top row.

The focused cell uses the double-outline treatment. The footer names the
focused action and states that selection opens confirmation and sends nothing.
Profile B guidance is `TAP: MOVE · DOUBLE: SELECT`; profile A guidance is
`HEAD: MOVE · TAP: SELECT`.

### Confirmation

The whole screen has a 4-pixel outer frame and a 1-pixel inset frame. It shows:

- `CONFIRM?`, or `REVIEW RETRY` when retry review is required;
- the selected action as the main title;
- `Task <request_id> · revision <version>`;
- focused `Confirm & send` and unfocused `Back` controls;
- `only this state may send` in the footer.

The identity line is part of the safety UI and cannot be omitted. Selecting the
action never sends; only deliberate activation in this state can send.

### Sending

An outlined centred status panel shows `SENDING` and
`Waiting for gateway acceptance`. It must not resemble success.

### Sent

An authored outlined circle and check geometry appear above `SENT`. Supporting
copy is `Gateway accepted this decision` and `Task completion is not claimed`.
The screen reports transport acknowledgement only.

### Delivery unknown

An outlined warning geometry appears beside `DELIVERY UNKNOWN`. Supporting
copy is `Review before retry` when retryable and `Back to dismiss` otherwise.
No success geometry is present. Retryable errors expose `Review decision`; a
second deliberate confirmation is still required before a retry can send.

### Stale request

The state heading is `REQUEST CHANGED`, the main title is `Read it again`, and
the supporting copy is `The revision you reviewed is no longer current.` plus
`No decision was sent.` The focused control is `Read current request`; `Back`
remains available.

### Rejected action

The state heading is `ACTION REJECTED`. Supporting copy is
`Action is no longer offered` and `No decision was sent.` Back dismisses the
state. The device never substitutes another action.

## Interactions

The renderer reflects, but does not alter, the existing input mapping.

| State | Navigation/open | Deliberate activation | Back |
|---|---|---|---|
| Attention | Opens request | Does not send | Returns quiet |
| Request | Opens action menu | Does not send | Returns attention |
| Action menu | Moves focus | Opens confirmation; does not send | Returns request |
| Confirmation | No implicit navigation send | Sends exactly once | Returns to actions |
| Result states | Opens documented recovery where available | Never bypasses review | Dismisses |

Head motion can move focus but can never confirm. The visual focus indicator is
updated synchronously with the state machine.

## Edge cases

- Quiet connected and quiet disconnected must remain visually distinguishable.
- Missing or malformed content shows a compact `DISPLAY UNAVAILABLE` error and
  emits nothing.
- A session mismatch shows `SESSION CHANGED` and instructs the user to restart
  the paired app. It never reuses the prior session's request UI.
- Long titles and context wrap only within their allocated regions. Action
  labels are limited by the common contract and never run outside a cell.
- One or two source actions are supported. No third source action is invented or
  drawn.
- Duplicate confirmation while sending cannot create a second decision.
- A restart never restores confirmation as an automatically sending state.
- All non-success states use geometry and explicit copy distinct from `SENT`.

## Acceptance gate

The visual gate passes only when all states can be inspected in MemoMind Studio
and the following are true:

1. request, action menu and confirmation are recognisably different layouts;
2. focus is visible without relying on colour;
3. confirmation is the only full double-framed state;
4. quiet is blank when healthy;
5. success, stale and delivery-unknown states cannot be confused;
6. title, context, controls and footer do not overlap at 600 by 350;
7. the user approves the glasses-side visual result.

Until this gate passes, functional simulator evidence remains valid but M2
visual parity remains **NOT APPROVED**.

# Halo Agent HUD state map

## Touchpoint: agent decision display

Agent HUD presents bounded agent requests and results; it does not display a
stream of model tokens. The seven AI-output categories are therefore mapped to
the device contract rather than simulated as chat behaviour the product does
not have.

| Required category | Halo treatment | Copy | Actions | Transition |
|---|---|---|---|---|
| Loading | Amber sending screen after confirmation | `SENDING...` / `WAITING FOR RESULT` | Long press closes without changing delivery state | Matching result -> Sent, stale or Rejected; transport uncertainty -> Delivery unknown |
| Streaming | No partial agent text is rendered; the current complete request remains frozen | No streaming copy | None | A later complete revision is handled as stale, never merged into visible text |
| Success | Green outlined circle and chosen action | `SENT` / `OK` / `LONG: CLOSE` | Long press closes | Close -> Quiet |
| Error | Red outlined delivery state | `DELIVERY UNKNOWN` / `CHECK / RETRY` / `RECONFIRM TO RETRY` | Double click reviews; long press closes | Review -> Confirmation; close -> Quiet |
| Partial | Malformed or incomplete requests are not presented as complete decisions | No request copy; attention is not raised | None | A later complete request may enter Attention |
| Uncertain | Red stale or delivery-unknown screen, with wording that does not claim an outcome | `STALE REQUEST` / `RELOAD REQUIRED` / `NOT ACCEPTED`, or the Error copy above | Reload/review when available; long press closes | Reload -> current request; review -> Confirmation; close -> Quiet |
| Empty | Blank black canvas by design | No copy | None | A valid request -> Attention |

## Edge-case review

- Interrupted transport never exposes half a request and never changes to Sent.
- Empty or malformed payloads stay quiet and emit nothing.
- Long text is capped and wrapped; the device never scrolls a decision behind
  the wearer's back.
- Inputs received while Sending cannot create a second decision.
- A newer revision cannot be silently substituted into an open confirmation.

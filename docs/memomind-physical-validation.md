# MemoMind One physical validation runbook

- **Status:** Ready to execute; not run on physical glasses.
- **Checked:** 2026-11-02.
- **Tracker:** [issue #10](https://github.com/RBraga01/agent-hud/issues/10).

PR #8 merged the experimental port after public-SDK builds and Desktop Studio
functional and visual checks. Those results are recorded in the
[simulator evidence report](memomind-m1-5-results.md). The paired phone result
used there is synthetic; this runbook does not claim a live Agent HUD gateway
connection or hardware validation.

## Entry gates

Record each gate as **PASS**, **BLOCKED** or **UNKNOWN** before attempting an
installation:

1. The MemoMind App account is authorized for **Settings → Memo Lab → Developer
   Workspace**, and the account that will scan owns the test application. A
   submitted interest form or a public SDK checkout does not prove access.
2. A physical MemoMind One is available, powered, worn and reported **connected
   in the MemoMind App**. Pairing in the phone's Bluetooth settings alone is
   insufficient.
3. Record the SDK commit, Desktop Studio version, phone OS, MemoMind App
   version, glasses model and firmware. Confirm that the SDK, App and firmware
   are mutually compatible before using an old package. Re-read the matching
   release's installation guide if any component has changed.
4. Build from the pinned public SDK with `platforms/memomind/tools/prepare-studio.ps1`.
   Its tests, GMP/MMPKG build and pair check must pass. Record both package
   SHA-256 hashes. Generated packages and raw logs remain outside Git.
5. Connect the phone and Studio computer over a mutually reachable LAN, and
   allow Studio through the local firewall. Keep the phone-to-glasses Bluetooth
   connection active throughout installation and testing.

## Install the exact pair

1. Import the complete public toolkit into Desktop Studio. Select the freshly
   built Agent HUD GMP and MMPKG together; verify the displayed names,
   versions and paired protocol. Wait for Studio to finish packaging and show
   the **current** QR code and installation address.
2. In the MemoMind App, open **Settings → Memo Lab → Developer Workspace**.
   Scan **Scan to open application**, or enter Studio's IP address and port
   manually. The phone downloads Studio's ZIP over LAN; the App checks account
   ownership and permissions before transferring the GMP to the glasses over
   Bluetooth. Studio must remain open until the download completes.
3. Confirm the App reports a successful start, the glasses display the intended
   build, and the paired phone page loads. A visible phone page alone is not a
   successful glasses test. Save the complete Studio ZIP, package hashes and
   version record for retesting.

This sequence follows MemoMind's [hardware setup](https://open-platform.memo-mind.com/docs/get-started/quickstart/hardware/?lang=en),
[QR installation](https://open-platform.memo-mind.com/docs/get-started/quickstart/lan-install/?lang=en)
and [device testing](https://open-platform.memo-mind.com/docs/test/private-testing/?lang=en)
guides. It requires an authorized account and real glasses; a Studio QR code
by itself does not satisfy either prerequisite.

## Minimum Agent HUD checks on device

Use invented requests and a counter on the phone; do not connect a live coding
agent for this validation.

| Case | Stimulus | Required observation |
|---|---|---|
| Quiet and request | Start, then deliver one test request | Quiet boot; attention indicator only after arrival; request text is readable on lens |
| Navigation | Move focus and open/select an action | Phone decision count remains zero until the separate confirmation is activated |
| Confirm and cancel | Confirm once; repeat with Back from confirmation | One correlated phone result and one `Sent` for the first run; zero decisions for the cancelled run |
| Stale and retry | Supersede revision during confirmation; inject ambiguous delivery | Old revision is blocked; retry requires fresh review and reuses the decision ID |
| Live Bluetooth recovery | At confirmation, disconnect and reconnect the phone while the **same GMP remains running** | No implicit send; old confirmation cannot resume; a fresh request is required |
| Lifecycle | Background/lock the phone, sleep/wake and reboot glasses, stop/restart the App | No replayed approval, duplicate listener, silent send or stale request presented as new |
| Physical input and display | Repeat taps, double taps, Back and head-motion input under normal wear | Navigation cannot confirm; no accidental double activation; essential text and warnings remain legible |
| Package identity | Stop/start, rescan the same ZIP, then update one component | App and glasses run the intended matched versions; no stale cache or one-sided update |

The package-selector restart in Desktop Studio is **not** the live Bluetooth
recovery test: it restarts both runtimes. Record an actual disconnect event on
an already-running GMP or leave that case **BLOCKED**.

## Evidence and decision

For each run, record the exact ZIP/package hashes, SDK/Studio/App/firmware
versions, device and phone model, input sequence, phone decision count, glasses
screen state, and time-correlated logs from both sides. Keep raw logs and photos
out of the public repository; publish only sanitized results and the evidence
level **CONFIRMED_ON_HARDWARE** where a physical observation supports it.

Stop if account authorization, App connection, version compatibility or paired
package identity cannot be established. A build, QR code or Desktop Studio
capture remains simulator/packaging evidence. If no device is available, the
physical gate remains **BLOCKED** without implying an implementation failure.

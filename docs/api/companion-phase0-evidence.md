# Companion Phase 0 implementation evidence

Gate 0.0 (the HTTP contract) is approved. This note tracks the server
implementation separately. The final Phase 0 gate remains subject to review.

`GET /v1/companion/snapshots/current` now requires an owner session even on
loopback. An auth-disabled gateway returns 403, and a paired-device token alone
returns 401. All JSON responses are non-cacheable. The response uses a fresh
gateway instance UUID, a monotonic effective version, strict legacy-task
normalization, source-health evidence and `decision_submission_enabled=false`.
The existing `/tasks` and feedback URLs are unchanged.

The poller records evidence per configured source under the same synchronization
boundary as its task update. An unverified source, expired evidence, failed
sweep, malformed task or unverified pushed slice forces `complete=false`.
Currently only the simulated feeder and a present, strictly parsed file feeder
can certify a successful read. GitHub, Claude, Codex and OpenCode feeder paths
can silently return an empty list after an internal read/parse failure; their
legacy behavior is preserved for the glasses, but they **cannot** certify a
complete companion snapshot yet. This is deliberate fail-closed behavior, not
evidence that those sources are empty.

The gateway selects its first paired device during the existing owner-authorized
pairing ceremony, persists that server-generated ID and does not silently
switch to another device after revocation. A revoked device disappears from the
snapshot and its token loses access. Multiple-device switching needs a future
explicitly contracted owner action; no client-supplied ID selects glasses now.

`last_authenticated_at` records paired-token activity only. Such activity
cannot make glasses `healthy`, start an absence timer or recover an unavailable
device. An optional trusted link checker, injected into the gateway rather than
exposed as an HTTP input, can record independent link checks. Its first verified
success yields time-limited `healthy`; a failure yields `unknown`; `unavailable`
needs two distinct failed checks at least 60 seconds apart after a prior
verified link. The most recent negative check remains valid for at most 120
seconds; after that `unavailable` becomes `unknown`, and a later negative check
starts a new absence run rather than reusing stale failures. A verified recovery
clears the failure run. A crashed or missing checker adds no evidence. Phone
reads never call it. Each check receives a monotonic sequence when it starts;
results from earlier checks are discarded if a newer check has started, even
when they complete out of order. The check result is scoped to the selected
paired identity, and a late result after revocation is ignored.
Pairing survives a restart; physical-link proof does not.

The default gateway does **not** install a physical link checker. Thus its
selected device remains `unknown`, even when it receives authenticated token
traffic. The simulated checker in tests validates gateway state transitions,
not physical Raven/Halo operation. Hardware validation is a later gate. The
mobile decision flag remains false throughout Phase 0.

Regression and HTTP integration coverage lives in
`tests/test_companion_endpoint.py`, `tests/test_companion_contract.py`,
`tests/test_feeder_evidence.py`, `tests/test_companion_presence.py`,
`tests/test_auth.py` and `tests/test_refresher.py`. It includes
authentication, schema validation, verified and incomplete empty snapshots,
malformed input, source failure/expiry, restarts, policy decisions, content
edits, pushed events, concurrent reads/sweeps, authenticated pairing,
device-token activity, two timed absence checks, recovery, revocation during a
pending probe, expiry of negative evidence, reversed completion order of
concurrent probes and restart without inherited physical presence. Unsupported
legacy feeders are explicitly incomplete by design; supporting them is not a
prerequisite for the Phase 0 gate. Review should focus on these behaviors and
the executed suite, not assume physical compatibility from simulated checks.

The pairing route also rejects a malformed JSON body before creating or
selecting any device; a regression test covers this write-after-error case.

Verification on 2026-10-19, local branch `feat/companion-gateway-phase0`:

- `.venv\Scripts\python.exe -m pytest -q --cov=agent_hud --cov=feeders --cov=stub_server --cov-report=term`: 961 passed, 2 skipped, 91.25% coverage.
- `.venv\Scripts\ruff.exe check .`: all checks passed.
- `.venv\Scripts\python.exe -m pytest tests/test_publication_hygiene.py -q`:
  4 passed.

These are local execution results, not independent review or a hardware
compatibility claim. The branch remains unmerged pending Phase 0 review.

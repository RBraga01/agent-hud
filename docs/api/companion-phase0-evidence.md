# Companion Phase 0 implementation evidence

Gate 0.0 (the HTTP contract) is approved. This note tracks the server
implementation separately; it does **not** close all of Phase 0.

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

`selected_device` remains null: pairing and token activity do not establish
which device is selected or prove a physical link. No healthy/unavailable
presence transition or mobile decision submission is enabled by this patch.

Regression and HTTP integration coverage lives in
`tests/test_companion_endpoint.py`, `tests/test_companion_contract.py`,
`tests/test_feeder_evidence.py` and `tests/test_refresher.py`. It includes
authentication, schema validation, verified and incomplete empty snapshots,
malformed input, source failure/expiry, restarts, policy decisions, content
edits, pushed events and concurrent reads/sweeps. The remaining Phase 0 work is
strict source-specific evidence for the legacy feeders and a server-bound
selected-device/physical-link observation path, followed by integration tests
against those real paths before declaring Phase 0 closed.

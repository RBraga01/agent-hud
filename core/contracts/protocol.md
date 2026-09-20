# Agent HUD cross-platform decision contract 1.0.0 (M0)

Normative definition, independent of programming language and transport. The
JSON Schemas define the wire shapes; `../conformance/` defines behavior. No
module under core is an executable runtime dependency.

## Vocabulary

| Field | Meaning |
|---|---|
| task_id | Stable identity of a task |
| revision | Version of that task observed by the user |
| action_id | Stable identity of an action offered by that task |
| decision_id | Unique identity of one logical decision, stable across retries |

IDs are non-empty ASCII identifiers (letters, digits, dot, underscore, colon,
hyphen), at most 128 characters. Revisions are integers 0..2^53-1, never booleans.
Task action IDs must be unique. The M0 action profile supports one or two offered
actions. Presentation text and task completion state are outside this envelope.
`payload` is optional in the base Decision schema; the M0 action profile rejects
it until a negotiated extension defines its meaning. It is never silently lost.

## Decisions and retries

A fresh decision ID is allocated only on deliberate confirmation. The complete
task/revision/action tuple is frozen at that point. Retry transmits the same ID
and content, with deliberate user activation; retry cannot change the action or
revision. A different logical choice requires a fresh ID and new confirmation.
Double confirmation while in flight emits once. Focus, select and cancel emit
zero decisions. A task update before confirmation invalidates the selection;
an update after sending cannot retroactively undo the transmission.

## Gateway results

Every result echoes decision_id, task_id and revision. Clients ignore results
that do not match the in-flight decision, including delayed results for older
decisions. Unknown or malformed results do not imply acceptance.

| Status | Meaning |
|---|---|
| ACCEPTED | Gateway accepted this decision; no claim about task completion |
| STALE | Gateway rejected an obsolete task revision; reload, never retry unchanged |
| INVALID_ACTION | Action is not offered; never retry unchanged |
| DUPLICATE | Same ID and content seen before; original_status is mandatory |
| ERROR | Acceptance is unknown or request invalid; reason explains the issue |

DUPLICATE preserves original_status (ACCEPTED, STALE or INVALID_ACTION). It
never upgrades rejection to success. Reusing an ID with different content is
ERROR/id_conflict, never DUPLICATE. Idempotency lookup precedes freshness checks:
an accepted decision can be replayed even after the task revision changes.
Results do not mutate the task in the client. Only a new task observation does.

Gateways declare their retention/durability boundary. The existing development
gateway is bounded in memory, so M0 does not promise exactly-once execution
across restarts or cache eviction. Production durability is a later milestone.

## Raven compatibility

The existing HTTP API remains unchanged. Canonical task_id maps to the task URL;
decision_id maps to legacy feedback.request_id; revision and action_id retain
their names. The canonical gateway compatibility adapter is callable locally;
M0 does not introduce a new public HTTP endpoint or replace authentication/TLS.
Legacy text/audio feedback is outside the M0 action profile.

## Transport bindings

Each implementation documents its own framing. Canonical fields never acquire
transport-specific meanings. Tests inject deterministic ID sessions; production
IDs must be unique across sessions/restarts. Copies of this directory must be
pinned to a source commit and checked byte-for-byte before claiming conformance.

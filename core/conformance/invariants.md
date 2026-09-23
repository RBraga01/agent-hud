# M0 conformance invariants

1. Focus/navigation never emits a decision.
2. Selection never emits a decision; confirmation is a separate event.
3. Confirm without a valid selected action is inert.
4. Cancel clears selection; a subsequent confirm cannot reuse it.
5. Only offered action IDs are allowed.
6. A changed revision invalidates an unconfirmed selection.
7. An older task observation cannot replace a newer revision.
8. One confirmation emits once; retry is explicit and reuses the entire decision.
9. ACK correlation includes decision_id, task_id and revision.
10. ACCEPTED and DUPLICATE/ACCEPTED never mean task completion.
11. STALE and INVALID_ACTION are terminal for that decision.
12. A task update after sending cannot erase the in-flight decision or its ACK.

Vectors use abstract user events. `initial` means the task is loaded and its
action menu open through platform navigation. `select` names an offered action;
`focus` may change focus but cannot activate. `confirm` is a deliberate confirm
gesture, never a shortcut that first selects an action. `retry` is a complete
deliberate platform retry gesture sequence (Halo review + confirm; Raven retry).
`update` carries a task observation, `result` a gateway response.

Compare every field in expected_transmissions, including repeated IDs on retry.
Compare unique logical decisions in expected_decisions separately. Null
expected_result means no correlated terminal result (e.g. still sending).
The deterministic ID factory yields m0-session:1, m0-session:2, etc.; production
uses fresh IDs. Test adapters translate events and observe output; they must
not implement their own decision lifecycle to make a vector pass.

Gateway vectors independently test duplicate lookup, ID conflict and outcomes.
Task completion and physical input recognition are intentionally not certified
by these vectors; each platform keeps its own UI/input/integration tests.

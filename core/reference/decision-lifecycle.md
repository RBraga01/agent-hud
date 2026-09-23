# Decision lifecycle (reference explanation)

The normative contract is in ../contracts/protocol.md and ../conformance/.
This document illustrates the lifecycle without prescribing an implementation.

```text
observed task -> selected action -> confirmation -> in-flight decision
                    |                    |                |
                  cancel              stale          correlated result
                    |                    |                |
                no decision         no decision     accepted / rejected / unknown
```

The confirmation captures the identity/version the user actually reviewed.
The gateway validates it against authoritative task state. These checks protect
different windows of time and both are required.

An uncertain delivery can be retried explicitly with the original decision ID.
The same user gesture cannot both select and confirm. Platform-specific screens,
focus, paging, audio review and transport remain platform responsibilities.

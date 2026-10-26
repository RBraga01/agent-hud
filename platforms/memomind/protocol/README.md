# MemoMind Agent HUD paired protocol

The application uses request channel `0x4148` (16712) and response channel
`0x4149` (16713). Transport acknowledgement is not a business result.

Protocol version 2 binds the repository-level task, decision and result identity
to the paired MemoMind transport. Its byte-exact C/JavaScript interoperability
vectors live in `vectors.json`.

Frame header:

```text
"AH" | protocol_version:u8 | message_type:u8 | payload_length:u16be
```

All single-byte text lengths are followed by that many UTF-8 bytes. Revisions
are unsigned 64-bit big-endian values restricted to JavaScript's exact integer
range, `0..2^53-1`.

Request payload:

```text
session_id:text8 | task_id:text8 | revision:u64be |
title:text8 | short_context:text8 | action_count:u8 |
repeat action_count times { action_id:text8 | label:text8 }
```

Decision payload:

```text
decision_id:text8 | task_id:text8 | revision:u64be | action_id:text8
```

Result payload, sent by the phone only after it has validated the decision:

```text
decision_id:text8 | task_id:text8 | revision:u64be |
status:u8 | original_status:u8 | reason:u16be_length+utf8
```

Status values follow the common result ordering: `ACCEPTED=1`, `STALE=2`,
`INVALID_ACTION=3`, `ERROR=4`, and `DUPLICATE=5`; zero means that no original
status applies. `DUPLICATE` must identify an original terminal result:
`ACCEPTED`, `STALE` or `INVALID_ACTION`. This correlated result is what moves
the glasses out of `SEND`; Bluetooth transport acceptance alone does not.

The canonical simulator fixture carries two actions and a fresh session ID.
Identifiers are ASCII canonical IDs up to 128 bytes (session IDs: 100), title
is limited to 63 UTF-8 bytes, context to 127, labels to 16 and result reason to
256. The state machine never invents an action outside the request.

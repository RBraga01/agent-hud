# Raven baseline before M0

- Git tag (local): `baseline/raven-pre-m0-2026-09-20`.
- Source commit: `fee2c30c5ff3fb84a1221847c805feee33bf26b7`.
- Working tree was clean before M0.
- Python 3.14.4, Windows, local Raven Framework available.
- Command: `.venv/Scripts/python.exe -m pytest -q --cov --cov-report=term
  --cov-report=json:docs/baseline-raven-coverage.json`.
- Result: **814 passed, 2 skipped**, 109.06 seconds, **91.07%** statement coverage
  (2,418 measured statements; 216 missed). Existing coverage exclusions apply:
  `app.py` and screen widgets are tested locally but not counted in coverage.
- The skips are recorded as skips, not passes or hardware evidence.

## Existing visual evidence retained

| Asset | SHA-256 |
|---|---|
| screens_day.png | B0FB5063191EB287145E3D276607183630704A93E88ECBC29D3F08BCB18DAE4D |
| screens_night.png | 26AD920AFFBD0C4B510F9608D4D67E37B6833C1BBE80D134B509D674A4143633 |
| walk_day.gif | 2F128FE003030453AF87C30EE3B8AF78A8375A78F40EA1A9E1CB82E9B334233B |
| walk_night.gif | 60D5DC128DAEEF47A28F5747F17FE01FA8A1876DA204F8CE148CB875180ECA1B |

`m0-screenshots/baseline/` contains new pre-change Qt captures of the actual
application: attention, action menu, confirmation and sending. Their clock read
10:28; the current replay fixes that clock so time does not create a false diff.
All fixtures are invented. Existing source images/GIFs remain unchanged.

## Behavior being preserved

Gaze focuses; RavenOS button activation drives navigation. Offered actions open
a separate confirmation. Only confirmation sends. ACCEPTED means gateway receipt.
The current HTTP feedback body retains `request_id` as its retry identity, and
task revision rejects stale answers. Screen composition and navigation remain.

## Defects exposed by M0 (intentional safety corrections)

1. A second direct `confirm()` callback on RESULT could allocate a new request ID
   and send again. Confirmation now checks screen, observed revision and action.
2. A lower-revision task observation could overwrite a newer one. Refresh now
   retains the newer task for the same ID, while respecting actual removals and
   clearing observations on an explicit gateway switch.

These edge cases changed; claiming literally unchanged behavior would be wrong.
The intended user flow remains visually identical.

# Padded BG Watch Task 4 — Fix Round 1 Report

## TL/DR

The Task 4 `0/160` result remains
`POSITION_ONLY_UNFIXABLE_UNDER_CURRENT_TOPOLOGY` as bounded offline
position-only evidence. The output is now explicitly a
`NOT_ATTACHABLE_SOURCE_PROFILE_AND_CANONICAL_BINDING_UNRESOLVED` pending
evidence packet, not a terminal-exclusion event and not a release-ledger
attachment.

## Finding corrected

The previous writer generated a private route identity, derived an event-style
digest, and wrote terminal-exclusion-shaped data. The current release-master
ledger checkpoint records `BASE_GAME_SOURCE_PROFILE_UNRESOLVED` and requires an
exact record/profile match before an event may affect a record. Consequently,
the previous data could not support the implications its field names suggested.

## Current contract

- Zero pass writes `pending_exclusion_evidence_packet.json`, never a candidate
  DAE or terminal-exclusion event.
- Pass writes only the selected candidate DAE, never the pending packet.
- The pending packet contains no `event_id`, `record_id`, `identity_sha256`, or
  `source_profile_id`; release-ledger validation therefore rejects it as a
  record rather than silently attaching it.
- Before it makes any prior-architecture statement, the writer pins and
  re-hashes `evidence/ARTIFACT_MANIFEST.json` and every one of its `36`
  registered artifacts. This includes `CLEARANCE_COMPARISON.md`,
  `evidence/four_way_clearance.json`, and
  `evidence/local_repair_manifest.json`.
- Immediately before writing, the writer independently compares both repeated
  JSON byte payloads and both selected-position hashes. A mismatch refuses the
  write.
- All four possible named output paths are preflighted and then written with
  exclusive-create semantics. A stale artifact is refused and left unchanged;
  no cleanup/deletion branch exists.

## Regression evidence

The post-hoc regression tests cover writer pass and zero-pass branches,
candidate-only-on-pass, pending-packet-only-on-zero, ledger non-attachment,
complete prior-artifact registration, stale-artifact refusal, and repeated JSON
or selected-hash mismatch refusal. They are post-hoc tests for this repair; no
historical RED result is claimed.

Fresh focused command and result:

```powershell
& 'C:\Users\Alan\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m pytest 'workstreams/padded_bgwatch_closure/tests/test_local_integration.py' -q
```

`10 passed, 1 skipped in 0.36s`

Fresh broader suite results:

- `workstreams/padded_bgwatch_closure`: `47 passed, 1 skipped in 1.20s`.
- `workstreams/release_master_ledger`: `99 passed, 1 skipped in 0.66s`.

## Scope preserved

No GR2, PAK, VisualBank, Lua, profile, installation, save, live game file, or
protected route was read for mutation or changed. The pre-existing ignored
event-style file was deliberately neither deleted nor overwritten; a fresh
empty ignored output directory is required for a later real run of this writer.

# Padded BG Watch Position-Only Closure — Public Checkpoint

## TL/DR

The current real-input result is `BLOCKED_SETUP`, not garment impossibility:
the reviewed target builder fails the unchanged `0.001 m` clearance gate at
five source vertices. No new parameter-grid search ran, no candidate was
emitted, and Task 3 remains incomplete.

## Current verified setup evidence

Frozen implementation: `f538a8615310d63abca31689c1e9108e76d4bc52`.
The tracked worktree was clean before both actual setup probes. The second
probe records and verifies unchanged input hashes and all ten ordered
implementation-file hashes before and after execution.

| Exact retained input | Bytes | SHA-256 |
|---|---:|---|
| Pristine Padded DAE | 6004823 | `DB6C143EE853385BA5A4FDEE9CF60E85030203856596256C37EE8A0D45AAA262` |
| BCB body GLB | 911216 | `51D4D723EB945CD16E0EF99296CFBD8050013D6FA74D863C5A7ACF962746328C` |

The production builder queried 593 rounded targets and raised
`TARGET_SETUP_CLEARANCE_NOT_MET` for these exact source IDs. Every failed
target changes its nearest body triangle after the offset; none is ambiguous.
Triangle IDs are zero-based indices in the verified parsed body, not game UUIDs.

| Source vertex ID | Initial triangle | Final triangle | Final signed clearance (m) |
|---:|---:|---:|---:|
| 546 | 18581 | 18569 | 0.0009992008220594594 |
| 548 | 18581 | 18569 | 0.0009991179627835238 |
| 4134 | 6337 | 6336 | 0.0008431459239153498 |
| 5725 | 5891 | 5894 | 0.0009829368380113472 |
| 7623 | 6393 | 6392 | 0.0009136607854053074 |

Current ignored evidence directory:
`local/generated/runs/certified-setup-f538a86/`.

- `blocked_setup_diagnostics.json`: 1139898 bytes, SHA-256
  `5D33CA9E5D484CF496A72FAAB8D27648DD16F681B9136F62017CE5F8A9130BC8`.
- `capture_setup_diagnostics.py`: SHA-256
  `CCA8DC32D8A1176DEEDA3C0D528FB0A28097B2D101F8DE704CA013F160BD7A8B`.
- The report retains all 593 actual production target queries, including
  source positions, original/final closest points and triangle vertex IDs,
  stored/geometric normals, projection, rounded target, clearance/margin, and
  ambiguity flags. It captures exception-frame data without replacing or
  modifying production functions. JSON emission rejects nonfinite values.
- The new setup record has `evaluated_grid_case_count=0`,
  `passing_case_count=null`, `task_3_complete=false`, and no candidate or
  attachable exclusion. This is not a `0/160` result.

## Required continuation

The one-shot target construction needs a reviewed correction that handles
changed nearest triangles without weakening the retained oracle or gates.
Certification of every actual target must succeed before the fixed 160-case
search can run twice from a new frozen implementation. The current failure
does not establish that position-only garment repair is impossible or exhausted.

Exact source-profile/canonical ledger binding is independently unresolved;
neither this setup report nor any older pending packet can change release scope.
No protected route, source asset, GR2, PAK, live game/profile, save, or Runtime
file was changed. No gameplay or release acceptance is claimed.

## Regression verification

At the frozen implementation, the portable Padded suite returned
`143 passed, 1 skipped`; the adjacent release-ledger/coverage/underwear/vanitybody
suite returned `161 passed, 14 skipped`. The real setup was exercised directly
twice and failed as described above; the portable suite's opt-in integration
skip must not be interpreted as a passing real preparation test.

## Historical checkpoint below — rejected, not current findings

The text below is retained as the historical checkpoint, not as accepted
geometry/exhaustion evidence. All its completion, `0/160`, and reopening-only
claims are overridden by the current `BLOCKED_SETUP` status above. The original
root search and `oracle-restored-r1` artifacts were independently rehashed and
preserved; neither the original event input nor the later pending packet is
attachable. In particular, final review rejected the restored-oracle run for
uncertified target construction and inconsistent failure-reason rows.

### Historical closure identity

| Field | Value |
|---|---|
| Source component | `HUM_F_ARM_BG_Watch_Leather_A_Body` |
| Mode | BCB, BCBPak absent automatic covering fallback |
| Source DAE SHA-256 | `DB6C143EE853385BA5A4FDEE9CF60E85030203856596256C37EE8A0D45AAA262` |
| BCB body GLB SHA-256 | `51D4D723EB945CD16E0EF99296CFBD8050013D6FA74D863C5A7ACF962746328C` |
| Source topology | 8,033 LOD0 vertices; 14,943 faces |
| Active vertices | 593; IDs SHA-256 `726ADFC0E20E00ADC0D8D4B6B0451D0939D7CF0FFCC1D904BFEAAE38A5220DF5` |
| Fixed coverage cohort | 2,800; IDs SHA-256 `A15EA818F106A23B44AC3DF26BD50AEC1FBBF3D4DCD157255E6FA0B2C95071E2` |
| ROI | 763 movable IDs; 617 fixed-boundary IDs |
| Parameter grid | 160 fixed cases: 10 scales x 4 fairness weights x 4 iteration counts |
| Serialization | Selected COLLADA POSITION payload only; six decimal places |
| Determinism | Two complete runs were byte-identical |

### Historical offline result — rejected

- Status: `POSITION_ONLY_UNFIXABLE_UNDER_CURRENT_TOPOLOGY`
- Passing cases: `0/160`
- Selected candidate: none
- Candidate DAE: none emitted
- Rejected historical restored-oracle run: `local/generated/runs/oracle-restored-r1/`
- Full search evidence SHA-256: `8C0E60533969E1BE492211E3F292D05890BD642E005FCFE750A6734B61998681`
- Pending non-attachable packet SHA-256: `31A881DAEEA757D3FC57FB3AFF4522FEF60972CA96E8D45A86A0179B7BCEDE24`
- Stored BCB vertex-normal array SHA-256: `533C492F576BDDD539DC5E7D696661A2E912C2E7E3901FFCCE7F018EB65979C0`

All 160 records fail `ACTIVE_CLEARANCE_NOT_MET`; record indices `37`, `38`,
`39`, `50`, `66`, `70`, `71`, `76`, `77`, `78`, `79`, `98`, `99`, `115`,
`134`, `135`, `150`, `151`, `156`, `157`, `158`, and `159` additionally fail
`ACTIVE_SURFACE_AMBIGUITY`. No record fails a moved-ROI ambiguity gate. The ignored evidence file
`local/generated/position_only_search.json` retains every per-case parameter,
serialized POSITION digest, and gate result.

### Historical bounded-disposition claim — overridden

The `0/160` result is retained as bounded offline evidence of the declared
automatic position-only architecture. It does not by itself authorize a
terminal-exclusion event: the current private route label cannot be attached to
a verified base-game source profile or a canonical release-ledger record.

The hardened writer emits only a
`NOT_ATTACHABLE_SOURCE_PROFILE_AND_CANONICAL_BINDING_UNRESOLVED` pending
evidence packet for a zero-pass run. That packet has no event ID, ledger record
ID, identity digest, or source-profile ID and cannot change release scope. It
registers and re-hashes the complete retained prior-evidence corpus, including
`CLEARANCE_COMPARISON.md`, its four-way clearance evidence, and its local-repair
evidence. A separately approved manual-remesh or licensed source-replacement
project remains the reopening path after exact source-profile and canonical
binding work.

The existing ignored `terminal_exclusion_event_input.json` from the earlier
writer was left untouched. The hardened writer refuses any pre-existing output
path rather than deleting or overwriting it, so that stale file is not a
current artifact and has no attachment or terminal-disposition implication.
The new writer must be run against a fresh empty generated-output directory to
produce its pending packet.

### Historical oracle-correction claim — not accepted

The current run replaces the earlier geometric-face-normal evaluation with the
retained closest-triangle oracle: signs use barycentrically interpolated stored
BCB vertex normals. The source and BCB local inputs were materialized and
hash-verified before parsing. The literal 160-case grid remains fixed in the
declared order; the two complete runs were byte-identical. These are current
offline findings only. Historical RED evidence for this post-hoc hardening is
unavailable; the regression tests were added after the prior implementation.

No GR2, PAK, VisualBank, Lua, profile, installation, save, or gameplay action
was created, read for mutation, or changed by this closure.

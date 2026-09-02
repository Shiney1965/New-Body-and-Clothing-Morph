# Padded BG Watch Position-Only Closure — Public Checkpoint

## TL/DR

The exact, hash-locked, topology-preserving position-only closure for
`HUM_F_ARM_BG_Watch_Leather_A_Body` completed two full deterministic runs.
Both runs produced byte-identical 160-case evidence with zero passing cases,
so the bounded automatic architecture is recorded as
`POSITION_ONLY_UNFIXABLE_UNDER_CURRENT_TOPOLOGY`.

This is offline position-only evidence only. It does not establish a corrected
GR2, PAK, installation, gameplay result, visual acceptance, or release
readiness.

## Exact closure identity

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

## Offline result

- Status: `POSITION_ONLY_UNFIXABLE_UNDER_CURRENT_TOPOLOGY`
- Passing cases: `0/160`
- Selected candidate: none
- Candidate DAE: none emitted
- Current restored-oracle run: `local/generated/runs/oracle-restored-r1/`
- Full search evidence SHA-256: `8C0E60533969E1BE492211E3F292D05890BD642E005FCFE750A6734B61998681`
- Pending non-attachable packet SHA-256: `31A881DAEEA757D3FC57FB3AFF4522FEF60972CA96E8D45A86A0179B7BCEDE24`
- Stored BCB vertex-normal array SHA-256: `533C492F576BDDD539DC5E7D696661A2E912C2E7E3901FFCCE7F018EB65979C0`

All 160 records fail `ACTIVE_CLEARANCE_NOT_MET`; record indices `37`, `38`,
`39`, `50`, `66`, `70`, `71`, `76`, `77`, `78`, `79`, `98`, `99`, `115`,
`134`, `135`, `150`, `151`, `156`, `157`, `158`, and `159` additionally fail
`ACTIVE_SURFACE_AMBIGUITY`. No record fails a moved-ROI ambiguity gate. The ignored evidence file
`local/generated/position_only_search.json` retains every per-case parameter,
serialized POSITION digest, and gate result.

## Bounded disposition

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

## Final oracle correction

The current run replaces the earlier geometric-face-normal evaluation with the
retained closest-triangle oracle: signs use barycentrically interpolated stored
BCB vertex normals. The source and BCB local inputs were materialized and
hash-verified before parsing. The literal 160-case grid remains fixed in the
declared order; the two complete runs were byte-identical. These are current
offline findings only. Historical RED evidence for this post-hoc hardening is
unavailable; the regression tests were added after the prior implementation.

No GR2, PAK, VisualBank, Lua, profile, installation, save, or gameplay action
was created, read for mutation, or changed by this closure.

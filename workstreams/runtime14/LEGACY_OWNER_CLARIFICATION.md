# Legacy owner representation - bounded R1 clarification

Authority: the pinned shared matrix's
`provider_registry_snapshot_api.legacy_v1_adapter` allows unresolved legacy
ownership and denies it API2 owner-collision/cleanup guarantees. Controller rulings
during Task 2 select the following explicit representation; this does not amend
the immutable matrix file or the historical R1 source pin.

- A general R1 legacy refit/revealing descriptor whose caller did not supply an
  explicit owner has `ownerModuleUuid=""` and `ownerUnresolved=true` in its canonical
  payload, stored descriptor, detached snapshot, and applicable rejected-attempt
  evidence. The empty string is deliberately not a Runtime/source owner identity.
- A known explicitly supplied owner remains a valid UUID with
  `ownerUnresolved=false` and a loaded-module requirement. This declaration alone
  does not establish API2 asset-ownership guarantees. `sourceModUuid` denotes the source-asset module, not the
  refit provider. Source UUID/version/credit are retained separately; queued source
  UUID dependencies are revalidated before activation.
- Unresolved-owner legacy map registration may preserve existing compatibility
  under the ordinary mutation gates. It cannot establish provider CCSV claims or
  owner-dependent cleanup, rollback, or profile guarantees. A requested body-CCSV
  claim without an owner is rejected, not attributed to Runtime or the source mod.
- This representation is **legacy-v1 only**. The later exact-build R2 native legacy
  bridge and API2 admission still reject unknown owners. No allowlist, source-free
  Alfira body, cleanup behavior, or API2 implementation is authorized here.

## Actual caller evidence

The existing SCO 2026-08-22 bootstrap (SHA256
`987F58B6694060B125FD1D6ED55F428E252FAD5206D73A20DCC2CF5074BF1B32`)
ignores the legacy external hook's return value inside a `pcall`. The inspected
Recluse 2026-08-30 bootstrap (SHA256
`40BB56EEC92B2664FAF4B3BBDDA1601CBA8FE83B98D9F41BB523270D48E69119`)
requires the return value to equal boolean `true`. Its exact source and map copies
are pinned as test fixtures by `contracts/recluse_caller.json`; this is source/API
evidence, not package or gameplay acceptance.

Therefore public legacy body/family/refit/revealing hooks preserve boolean first
returns, exact status second, and structured diagnostic third. Internal registry
results remain structured. A queued descriptor may be accepted as metadata, but
no new active maps, character writes, Runtime ACTIVE/READY claim, or gameplay
acceptance follows. Immutable historical provider `registered` log messages are
not activation evidence; the Runtime snapshot/status is authoritative.

## Recovery boundary

The pass-through specification's missing-original recovery prose does not create
a write exception for an effective-External/blocked record. Validated
`!cm_seterace` recovery is available only for already-managed authorized records.
An existing authoritative KNOWN_ORIG entry or a clean pre-management baseline is
required when originals are missing; a supplied GUID is never promoted to trusted
original merely because the user entered it.

For schema-6 migration only, a structurally valid saved `AppliedCcsv` plus its saved
`CvGuid` is the narrow recorded-write proof required by the shared matrix. That
proof is not physical asset ownership. It permits the exact legacy.runtime claim
even when a Tiefling provider resource is absent; it does not infer ownership from
`DesiredCcsv`, the live visual list, or unrelated saved visuals, and never borrows a
live CvGuid to replace missing saved provenance.

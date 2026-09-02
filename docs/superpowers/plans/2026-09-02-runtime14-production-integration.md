# Runtime 1.4 production integration implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Implement each task with strict test-driven-development and independent review. Do not substitute Python models or source-text assertions for executing the real Lua entry points.

**Goal:** Produce the actual offline-tested R2 Runtime source, preserving protected payloads and the accepted provider, with schema-7 ownership/pass-through, owner-aware APIs, exact legacy compatibility, and truthful physical dependency gates. This is a dependency of the complete whole-mod test PAK release, not an independent completion of that goal.

**Architecture:** Compose the verified R0 package with an explicitly copied pure R1 source overlay and independently qualify the complete R1 behavior. Develop R2 in this isolated worktree; never merge the cleanup branch. Use a common transactional provider registry and production Lua adapters. Canonical physical/source-profile validation is offline; Lua validates the observable module/resource contract. Accepted legacy descriptors are imported only from a build-verified allowlist. Undefined body geometry, source profiles, permission, and gameplay remain explicit release dependencies, not permissive defaults.

**Tech stack:** Existing BG3SE Lua modules, Lua executable behavior harnesses, Python/pytest for source/package provenance and orchestration, PowerShell and pinned Divine for isolated package readback.

## Authorities and isolated state

- Worktree: `New-Body-and-Clothing-Morph/.worktrees/clothmorph-runtime14`, branch `codex/clothmorph-runtime14`, start `de9d5a8c410c822425aa3920d9c16c6a47a50094`.
- Parent shippable specification: `ChatGPT Work Files/ClothMorph_Shippable_Release_Program_20260830/docs/superpowers/specs/2026-08-30-clothmorph-shippable-release-program-design.md`, especially sections 5-7, 11, 13-16.
- Normative shared matrix: `ChatGPT Work Files/Cross_Spec_Architecture_Review_20260830/SHARED_RUNTIME_LINEAGE_MATRIX.json`, SHA `5134237A6AD8F6F5BDB1721EE279A07A336727F9E88119CCB3B4B320D9D19A67`. It overrides contradictory version, READY, and rollback prose in older specifications.
- Pass-through design: `ChatGPT Work Files/Divine_Curse_ClothMorph_Interaction_Audit_20260830/docs/superpowers/specs/2026-08-30-clothmorph-external-pass-through-design.md`, SHA `02EA4E40D415A3EB5DD2E4C6DDFA6F87C8BBF4ACD9C9834E6D4097ED03E212C0`.
- Current correction: `docs/superpowers/specs/2026-09-02-alfira-physical-dependency-correction.md`. The old Alfira dependency-free body adapter is not an approved implementation input.
- Pure R1 reference only: separate `bcb-cleanup-runtime/workstreams/bcb_cleanup_runtime/runtime/r1_foundation`; source worktree stays clean at `cf62d7fe2953bdda376c2d6df94c3968dc97ec07`. Exact twelve-file manifest SHA `DEAFCB8734AB3558D490253BD00F99226179BEB758F6277BAC62A27A2B70DD0A`; allowed delta SHA `A989386BE8ADCCA6E92CF195963EAE12C13BCD04CDDBE85C7CFA08BEE8DC67A7`.
- Fresh isolated repository baseline: 418 passed, 14 skipped. No Runtime-specific implementation is implied by that baseline.

## Hard boundaries

- No live BG3 file, profile, save, application, accepted provider, protected route, main checkout, or separate-project modification. Never write an LSV offline.
- No R1C cleanup API, cleanup transaction, tombstone, removal workflow, or cleanup-canonical implementation in R2. Reading/rejecting a non-idle cleanup state is defensive gating, not cleanup functionality.
- No pull, merge, PR, installation, activation, or remote action in this plan. The final user-authorized fork-only push is a separate final release step.
- No source-owned path overwrite. Changed/unaccepted consumers require new owned resources and exact route binding under the protected registry.
- No permanent Tick, recurring timer, UI polling, equipment refresh during External restoration, third-party CCSV removal, or silent Vanilla recovery from explicit External.
- Synthetic fixtures never establish exact source/gameplay/permission acceptance. Opt-in real-source tests fail clearly when inputs are missing or drift; ordinary public imports/tests do not read workstation paths.
- No full test PAK until source-profile/geometry/permission/ledger gates for that package are independently satisfied. A source-only Runtime harness can progress while those other tasks remain open.

## Task 1: Freeze and compose the actual R0-to-R1 source baseline

**Files:** new `workstreams/runtime14/{__init__.py,.gitignore,provenance.py}`, `contracts/lineage.json`, `runtime/r0_reference/`, `runtime/r1_foundation/`, `tests/test_provenance.py`, `tests/lua/`, and ignored `local/` evidence/config.

**Interfaces:** `verify_lineage_inputs(config) -> VerifiedLineage`; `compose_runtime_stage(verified, output) -> StageManifest`. Verification is pure read-only; composition is exclusive-create into a validated isolated destination. Typed verified values bind actual bytes, not caller labels.

- [ ] RED: wrong R0 digest, wrong pure-R1 file/digest/count, traversal/casefold duplicate, altered protected data, nonempty destination, cleanup-code inclusion, and unknown overlay path are rejected.
- [ ] Hash exact R0 PAK `6610090CEE01091F802273D70FAEE071DCBA891900D77479ABBD828FCDDC60C6`; copy, freshly list/extract into an empty ignored directory, reconcile every path/byte count/hash. Hash source before/after; never rebuild R0.
- [ ] Verify the twelve pure R1 files and copy only that manifest-bound overlay. Read-only reference use must leave the cleanup worktree HEAD/status unchanged. Do not cherry-pick or import its whole workstream/tests/contracts.
- [ ] Preserve full R0 data/GR2/VisualBank/CCSV/refit-map manifest. Commit only project-owned source/metadata and bounded test support; proprietary/generated source payloads remain ignored inputs.
- [ ] Port the existing pure R1 Lua harnesses into this workstream with explicit source roots and source hashes. Execute them from this isolated copy, not inside the separate cleanup worktree. Mark mocked modules and uncovered real-R0 paths explicitly.
- [ ] Add exact accepted-bootstrap API-1/API-2 controls and decoded physical-dependency fixtures from the controller probe. Assert that a provider-owned VR with a missing external mesh is not a physically complete body.
- [ ] Run public tests without local config plus explicit exact-source tests. Record manifest/provenance and actual failures; do not broaden hashes or weaken assertions to make reused code green. Commit and independent review.

## Task 2: Qualify and complete production R1 ownership and user controls

**Files:** new revisioned `workstreams/runtime14/runtime/r1_qualified_delta/` Lua/MCM overrides, `contracts/r1_qualified_allowed_delta.json`, a separately verified qualification composer, and production-bound Lua integration fixtures/tests. Source-owned overrides of R0 `EquipRace.lua`, `BodyFamilyEquipRace.lua`, and `BodyFamilyRegistry.lua` are allowed only where behavior changes are required. `runtime/r1_foundation/`, the original `contracts/lineage.json`, and all historical input pins remain immutable references.

The qualification composer consumes a freshly verified Task-1 R0-to-R1 stage and applies only the new allowed delta into another exclusive destination. It must preserve all historical references and protected data hashes, reject unknown paths/modified receipts, and bind the new source revision and output manifest independently. Later R2 changes use another distinct revisioned delta; they never rewrite the pinned R1 source to make a test pass.

**Interfaces:** exact `SetCharacterMode`, legacy `SetDesiredBody` delegation, `SetMasterEnabled`, `GetOwnershipStatus`, immutable registry snapshot, central non-exported mutation authorization, schema-7 persistent records.

- [ ] Build a requirement-to-test matrix for every pass-through specification section 13.1-13.3 invariant and shared schema/master/ownership field. Existing review-clean snippets do not waive uncovered requirements.
- [ ] Record the two nonblocking Task-1 review notes: read-only, fully verified hard-linked input files are allowed (symlinks/reparse redirects are rejected); historical harness hashes in the immutable lineage contract are not current adapted-file hashes. Add a separately labelled adapted-harness manifest/test rather than editing historical pins. Neither note grants unique input-file ownership or live mutation authority.
- [ ] RED then implement exact four-choice parsing, managed-only cycle, `External / Pass-through` label, unbound External hotkey, host-only master command/MCM, owner-targeted character requests, read-only diagnostics, and truthful distinct version fields.
- [ ] RED then implement idempotent pre-mutation migration; preserve original fields/legacy claimed CCSV only; reject minted-as-original, missing trusted originals, wrong CvGuid, malformed schema, and stale provider claims.
- [ ] RED then implement shared-CV arbitration using real body/CCSV paths: mixed External/managed claims restore shared baseline and use owned per-character fallback for managed claimants. No last-writer-wins or third-party visual deletion.
- [ ] Exercise production load/level/equip/armour-set/tattoo/debug/provider callbacks and delayed managed refresh callbacks with spies. Gate before gameplay reads/writes; explicit restoration uses bounded internal capability and never refreshes equipment.
- [ ] Persist every transition before writes; inject failure/interruption at each phase, late/unavailable character, cross-save process writes, master-on partial success, third-party visual additions, and repeated restore. Verify exact state/readback rather than success booleans alone.
- [ ] Complete legacy body-family/refit/revealing registration queue behavior under ordinary master-off without active map/character writes. Do not equate a false-return early exit with successful queued registration.
- [ ] Re-run real-R0 managed-mode regression harnesses and byte-check protected maps/payloads. Commit and independent review before R2 work.

## Task 3: Implement owner-aware R2 external and body provider registries

**Files:** `ProviderRegistry.lua`, new focused descriptor/source-contract modules if needed, body registry/map commit adapters, status exports, Lua/Python canonical-contract fixtures.

**Interfaces:** `RegisterExternalRefitProviderV2`, `GetExternalRefitProviderStatus`, `RegisterBodyFamilyProviderV2`, `GetBodyFamilyProviderStatus`, `GetProviderRegistrySnapshot`. Exact shared-matrix result/snapshot fields are authoritative.

- [ ] RED strict complete descriptor validation: owner/family/provider identity, supported tuples, exact maps/counts/exclusions/revealing subset, source-profile/resource digests, required/forbidden UUIDs, body claims and resource manifest. Reject unknown fields/types, duplicate/ambiguous UUIDs, cycles/nonfinite data, and inconsistent counts.
- [ ] Establish one canonical serialization contract with executable cross-language golden/negative vectors. Preserve array order where semantically meaningful; do not call approximate JSON serialization RFC8785 compliant.
- [ ] Separate offline physical PAK attestations from Lua module UUID/version/resource checks. Missing/unreliable/conflicting observation fails closed; neither a supplied hash nor a successful resource lookup proves physical ownership.
- [ ] RED atomic preflight/commit rollback, base-map priority, same/different owner collisions, body-resource collisions, repeated same/different digest, queue validation and ordered revalidation, changed environment, schema reload, and rejected attempts. No partial maps or false READY.
- [ ] Unchanged queued digest activates at most once on explicit enable; External characters are never reapplied. Snapshot is a deep copy with exact active/queued/rejected owner/resource evidence and restart state.
- [ ] No in-process unregister/profile swap; report restart required. Technical registration validity is distinct from permission/distribution state.
- [ ] Execute actual entry points and injected map-commit failures; independently review after full tests and commit.

## Task 4: Bridge immutable accepted legacy providers into truthful API 2

**Files:** new `LegacyProviderAdapter.lua`, build-verified allowlist contract, bootstrap wiring, exact legacy bootstrap fixtures, compatibility tests.

**Architecture ruling:** an exact build-verified native descriptor import is the selected implementation candidate for legacy scripts whose own API-1 guard prevents any API-2 call. Global `BodyFamilyApiVersion` stays 2; no provider bytes or shared global are temporarily changed. The importer must pass through the same registry/gates as an ordinary v2 descriptor and remain explicitly labeled legacy_v1 in evidence. Unknown providers are not automatically imported.

- [ ] RED exact accepted Tiefling script refuses API2 even when old hooks exist; separately prove allowlisted native import works under either event order without double activation or reapply. Retain the bootstrap's observed warning as compatibility diagnostics, not a success line.
- [ ] Build allowlist from exact package/source descriptor/map hashes, owner UUID/version, and resource graph. Cover the accepted-current Recluse provider separately; do not copy mutable caller tables or infer an owner from a display name.
- [ ] Reject wrong descriptor/owner/version/resources, partial family/refit registration, same family from another owner, absent provider, wrong physical build manifest, forbidden profile, and changed profile after queueing.
- [ ] Preserve accepted Tiefling Vanilla/SBBF/BCBPak-present route identities. The actual BCB dependency UUID is `1d24059d-ff23-4a79-8892-57c85d512416`; no unconditional source-free body claim.
- [ ] A no-BCB-source Alfira correction may register only after a separate reviewed exact target/resource/permission contract exists. Its absence stays an explicit unresolved release dependency; do not declare the existing fallback a completed fix.
- [ ] Run genuine provider scripts and production Runtime Lua, including saved/fresh Tav and Alfira-model controls, External/master-off, load/reload, missing dependencies, and idempotence. Preserve accepted PAK hash. Commit and independent review.

## Task 5: Complete schema-7 provider transitions and safe rollback refusal

**Files:** focused provider-transition/history module, ownership/state/bootstrap wiring, rollback module, failure-injection Lua fixtures.

- [ ] Implement exact shared forward/reverse phases with non-exported transition capability, same-CvGuid attestation, exact owned-CCSV removal, new-baseline capture, append-only HistoricalOriginals and exactly one effective entry, resource readbacks, and last-effective rollback.
- [ ] RED every phase interruption, changed CvGuid/source/owner/digest, unavailable character, third-party visual preservation, write/readback failure, reverse rollback failure, and save-load resumption. Never auto-apply while a provider transition is non-null.
- [ ] Preserve disposable-new-save-only BCBUniqueTav boundary; the legacy Tiefling identity, including a tombstone, remains a blocker for that new-provider profile. Do not migrate the inspected legacy saves.
- [ ] Implement `PrepareRuntimeRollbackV1` only within the normative allowed lineage/target/mode contract, with explicit refusal otherwise. Ordinary master-off is never package-downgrade readiness; no offline save rewrite or invented PREPARED checkpoint.
- [ ] Run full schema/provider/master/control/bootstrap regressions, independent review, and commit. No cleanup API or live transaction is included.

## Task 6: Freeze R2 source and verify the release integration boundary

**Files:** R2 metadata/Config diagnostics, immutable stage manifest and expected delta, portable verification runner and Runtime test-card section.

- [ ] Set exact R2 metadata: same Runtime UUID, package 1.4.0.0/Version64 36591746972385280, code v4.23-api2, schema7, SE29 in Config only, PassThrough1, ExternalRefit2, BodyFamily2, Snapshot1, Cleanup0. Preserve metadata dependencies except separately reviewed required changes.
- [ ] Compose from a clean committed source snapshot; validate every file, expected-only source delta, unchanged protected binary/refit-map bytes, all Lua syntax and executable harnesses, no cleanup/polling content, and exact legacy allowlist/resource closure.
- [ ] Independently audit requirements against actual production code/test coverage. Resolve findings through strict RED/GREEN fix waves; unresolved functionality is not hidden by stage-manifest success.
- [ ] Report package eligibility per source profile, including every missing Alfira target, source/permission/geometry contract. Build only through the whole-mod release packager after its gates; do not install/activate anything.
- [ ] Hand off Runtime test-card cases with gameplay NOT RUN and exact future artifact identities when built. This plan cannot grant gameplay pass, whole-mod release completion, or GitHub publication by itself.

## Completion boundary

This plan is complete only when its real Lua source and all named offline contracts are independently verified. A required unresolved Runtime behavior or acceptance dependency keeps the affected task and plan incomplete; recording that dependency is progress, not completion. The overall goal remains active until all source/route/permission/geometry/package/gameplay dispositions and the complete fork-only test deliverables are satisfied. A green synthetic harness is not a playable Alfira fix.

# Task 1 - verified immutable Runtime lineage composition

Status: implementation complete, awaiting independent review. This is not R1 full
qualification, Runtime 1.4 completion, a playable Alfira fix, or package eligibility.

## Verified source evidence

- Exact R0 package: `6610090CEE01091F802273D70FAEE071DCBA891900D77479ABBD828FCDDC60C6`.
- Controller R0 freeze manifest: `B5C7EC104C308882CC5F33CC0907F13043CC2DEB7E9F9B8666F8825BB8DE0860`.
- Controller pure-R1 copy manifest: `98E833E63CF9D8274D21E9F9C986FFC34F004499C013BF7322C2F9603A0CA722`.
- Original pure-R1 manifest: `DEAFCB8734AB3558D490253BD00F99226179BEB758F6277BAC62A27A2B70DD0A`.
- Portable authority file `contracts/lineage.json`, LF bytes: `48B6AA013666E00B720909B2139D66820AF6C739F640CAD8561F2E697FCE665F`.
- Canonical sorted-JSON authority digest in stage receipts: `8C263ED0FADD7FBAB402503B23FAC64336DFB598F04245F89D4458BFC5F1D1EB`.

Fresh exact-source verification obtained the complete 739-file listing using the
pinned Divine executable and hashed every extracted file. Composition produced
745 files, 377699277 bytes: six exact replacements, six additions, and 733 unchanged
R0 files. No protected data/GR2/VisualBank/CCSV/refit-map file was changed.

The first retained result is `local/stages/task1-initial.manifest.json`, SHA-256
`9871653D606135F0DCA128EB4A26310F80C7E1683B4BCA0E580C2C36D6621131`.
Later test runs create new uniquely named stages and manifests; none reuse or erase
the first result. These ignored artifacts contain source paths and are not shipped.

## Verification performed

- Portable workstream suite: **42 passed, 3 skipped**. Skips are the two explicit
  real-source integrations and Windows host refusal to create a symlink fixture.
- Explicit actual-source integrations: **2 passed in 39.23 s** on the first run.
- Final complete invocation including actual sources and inherited release-master,
  coverage, underwear, and vanitybody suites: **462 passed, 15 skipped in 37.97 s**.
- Real Lua baseline harnesses, both copied overlay and composed stage:
  `TASK2A_LUA_PASS 13/13`, `TASK2A_BOOTSTRAP_RED_GREEN 26/26`,
  `TASK2B_BOOTSTRAP_RED_GREEN 15/15`.
- Lua syntax parsing: **20 source files passed** in the composed stage.
- Fresh index checkout under `core.autocrlf=true`: **42 passed, 3 skipped**.
- Fresh index checkout under `core.autocrlf=false`: **42 passed, 3 skipped**.
- Cached `git diff --check`: clean. Exact accepted bootstrap EOF whitespace is
  preserved with a narrowly scoped attribute, not removed or rehashed.
- Separate cleanup worktree: clean at `cf62d7fe2953bdda376c2d6df94c3968dc97ec07`.

The exact accepted provider package, all seven extracted files, and decoded
VisualBank were independently hashed and checked during the integration test.
The real bootstrap executes API1 registration but refuses API2 before registration.
Its BCB mesh reference is absent from the accepted provider and R0 inventories;
no inference about the complete active profile or save-state cause is made.

## Task 2 handoff and exclusions

Keep `runtime/r1_foundation/`, `runtime/r0_reference/accepted_tiefling_bootstrap.lua`,
and `contracts/lineage.json` immutable historical references. Task 2 should consume
`verify_lineage_inputs(config) -> VerifiedLineage` and the resulting
`compose_runtime_stage(verified, output) -> StageManifest`, then use a separately
revisioned qualified-R1/R2 overlay with its own explicit allowed-delta contract.
Do not overwrite the historical source files or broaden their original hashes to
make future behavior changes pass this checkpoint's tests.

Complete original R0 assets and Lua are available in the verified ignored R0 input
and composed stage. They are not automatically loaded by public imports, and no
full binary payload is committed. The readme lists exactly which R0/engine boundaries
the narrow harnesses mock. Those uncovered paths and the missing `SetCharacterMode`
and `GetOwnershipStatus` surfaces remain Task 2 requirements.

No later task, cleanup code, PAK build/install/activation, live application/profile/
save mutation, source-owned resource overwrite, Git pull/merge/PR, or remote action
was performed.

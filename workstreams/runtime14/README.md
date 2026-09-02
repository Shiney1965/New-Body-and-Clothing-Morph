# Runtime 1.4 workstream - Task 1 baseline

This is an offline source-composition checkpoint, not the Runtime 1.4 implementation,
an Alfira fix, a package, or gameplay acceptance. It preserves the exact accepted R0
data and overlays only the twelve designated pure-R1 source files. The separate
cleanup project is not an execution dependency and is never modified.

## Trust and composition

`verify_lineage_inputs(config)` accepts exactly four absolute input paths:
`r0_package`, `r0_root`, `r1_root`, and `divine`. No digest, mode, permission,
lineage label, or caller-supplied acceptance flag is configurable. The repository
contract pins the package, complete extracted inventory, tool, and exact overlay.
It also records the controller freeze/reference/matrix provenance digests.

Verification reads all actual bytes, obtains a fresh listing from the pinned
Divine executable, and checks the complete path/size/hash sets. It rejects unsafe
Windows paths, casefold duplicates, links/reparse paths, unreadable inventory,
extra/missing files, or byte drift. The raw controller manifest paths are not
portable authority; only their recorded hashes and sanitized file metadata are
tracked here.

`compose_runtime_stage(verified, output)` repeats verification. It accepts only a
new destination strictly below this workstream's `local/stages/`, never an existing
directory or an input-overlapping destination. It copies verified bytes once,
readbacks the complete output, and revalidates inputs before returning a manifest.
A constructed/edited dataclass is not a write capability. A failed partial stage
is retained without an accepted manifest; it is not reused or automatically deleted.

Production source assets remain in ignored input/stage directories. The tracked
`runtime/r1_foundation/` files are exact project-owned source copies, not edits to
the separate cleanup worktree. Git text conversion is disabled for exact source
copies so their pinned bytes are portable. The accepted provider bootstrap is a
byte-exact project-owned historical fixture, not a patched provider.

## Test modes

Portable tests: `python -B -m pytest workstreams/runtime14/tests -q -p no:cacheprovider`.
Set `CLOTHMORPH_LUA` to Lua 5.4 if it is not on PATH. Public tests never load local
configuration implicitly. Synthetic filesystem tests explicitly substitute a
test-only authority through pytest monkeypatching; their receipts are permanently
labelled `SYNTHETIC_TEST`, not actual R0 verification.

Exact-source tests: explicitly set `CLOTHMORPH_RUNTIME14_INPUTS` to an absolute JSON
configuration path. Missing/drifted configured files fail, not skip. The JSON holds
`inputs` with the four paths above, `r0_freeze_manifest`, `r1_copy_manifest`,
`provider_root`, `provider_package`, `visualbank_readback`, and `stage_output`.
`stage_output` is a stem under `local/stages/`; each run appends a unique suffix,
preserving previous evidence. The completed stage manifest and Lua outputs are
written adjacent to, not inside, the package source tree. The ignored controller
configuration is `local/inputs.json` on the originating workstation.

## Actual coverage and remaining gaps

The inherited, bounded Lua harnesses execute the real R1 `BootstrapServer`,
`StateSchema7`, `OwnershipLedger`, `MasterState`, `R1Foundation`, `ProviderRegistry`,
`RuntimeRollback`, and `MCMIntegration`. Their explicit source-root argument works
against both the copied overlay and the complete composed source stage. Input
source hashes are checked by Python before and after their public execution.

The bootstrap fixture mocks `Shared`, `TattooPolicy`, `TattooStateProbe`,
`TattooDiagnostics`, `EquipRace`, `BodyFamilyRegistry`, `BodyFamilyEquipRace`,
`Targeting`, `SharedTemplateProbe`, BG3SE, Osiris, and MCM. Client bootstrap, actual
R0 body/refit/targeting behavior, real engine events, meshes, saves, and gameplay
are not qualified by these harnesses. `SetCharacterMode` and `GetOwnershipStatus`
are known missing R1 surfaces reserved for Task 2. R1 broad pass-through compliance
must not be inferred from the preserved narrow tests.

The genuine accepted Tiefling script registers under API1 but refuses API2 before
making any registration call. Its BCB VisualResource references an external BCBPak
GR2 absent from both the accepted provider and R0 package manifests. The exact-source
test additionally hashes the real package/extracted files/decoded VisualBank and
parses the real reference. A defined VR is not proof of physical body completeness;
no source-free adapter or active-load-order conclusion is made.

No Runtime behavior has been changed in Task 1. Tasks 2-6 and the broader release
source, route, permission, geometry, package, and gameplay gates remain open.

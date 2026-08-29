# ClothMorph Class-First Coverage Design

**Date:** 2026-08-29  
**Status:** Proposed for user approval  
**Project:** Body and Clothing Morph for BG3  

## 1. Goal

Replace sample-driven garment work with a class-first system that accounts for every eligible base-game, SCO, and Sindae wearable, separates true `Underwear` items from `VanityBody` clothing, corrects confirmed defects without changing protected garments, and produces bounded gameplay waves with exact route evidence.

The design must prevent an item from falling outside the plan merely because it was not selected for an earlier sample.

## 2. Scope

### 2.1 Included sources

- Base-game wearables relevant to the true underwear-slot task.
- Scantily Camp Outfit (SCO) wearables.
- Sindae wearables, including BCBPak, BCBScantily, Sindae Imported Outfits, and Sindae Texture-backed garment families when they supply or support a wearable source.
- Existing ClothMorph Runtime and source-specific add-on routes needed to classify or protect the included items.

### 2.2 Included workstreams

1. True-underwear classification and package rebuild.
2. VanityBody classification and exact correction of confirmed groin/genital defects.
3. Complete SCO/Sindae garment coverage ledger and class-based test queue.
4. Reconciliation of existing targeted work, including Recluse, Bard, Soul Vest, Butler, Oathbreaker, BCBScantily, and prior Sindae samples.

### 2.3 Excluded from automatic propagation

- A garment is not changed merely because its filename, display name, or appearance suggests underwear.
- A garment is not changed merely because another garment shares a broad category such as dress, robe, bodysuit, or armour.
- A passing garment is not regenerated as a side effect of correcting a related garment.
- Strong-body, unsupported-race, and non-BT1 routes remain outside a package unless separately proven and approved.

## 3. Binding identity model

Each concrete wearable route is identified by the tuple:

`source module UUID + root template UUID + stats entry + effective equipment slot + source VisualResource UUID + body family`

Display names are annotations, not identity.

When a root template and a named stats entry disagree, both creation paths are recorded separately. The path actually used by a spawn command or treasure/root-template reference controls the gameplay classification for that test.

## 4. Equipment-slot classification

### 4.1 True underwear

An item belongs to the true-underwear workstream only when its effective stats inheritance resolves to:

`Slot = "Underwear"`

The resolver must follow `using` inheritance until the slot is found. It must record the inheritance chain as evidence.

### 4.2 Vanity clothing

An item belongs to the VanityBody workstream when its effective stats inheritance resolves to:

`Slot = "VanityBody"`

This includes camp and vanity clothing even when the item is visually lingerie-like or its internal name contains terms such as thong, bikini, panties, underwear, or bodysuit.

### 4.3 Root-template mismatch rule

If a root template hard-codes `ARM_Vanity_Body_Citizen` while a separately named stats entry inherits `ARM_Underwear`, the root-spawned item is classified as `VanityBody` and the named-stats item is classified as `Underwear`. They are separate ledger records even if they share a mesh or display name.

Known examples requiring this split include Wedding Body Suit and Satin Thong.

## 5. Workstream A: True underwear

### 5.1 Inventory requirement

Inventory every base-game, SCO, and Sindae wearable whose effective slot is `Underwear`.

For every item, record:

- source mod, folder, name, and UUID;
- root template UUID and stats entry;
- complete stats inheritance chain;
- effective slot;
- source VisualResource UUID and source path;
- native body form;
- existing Vanilla, SBBF, and BCB routes;
- route provenance and mesh hashes;
- gameplay status;
- disposition and evidence paths.

### 5.2 Package rule

Retire the current `ClothMorphUnderwearBCBPak_TEST.pak` as a true-underwear candidate because it was built from a mixed set that included VanityBody routes.

Build a new true-underwear TEST PAK containing only verified `Underwear`-slot records. It must declare exact dependencies for every source module and the ClothMorph Runtime. Dependency folder, name, UUID, and `Version64` must match the installed source metadata exactly.

### 5.3 Route behavior

- Vanilla and SBBF receive new or accepted targets only when the source form requires them.
- Native BCB passthrough remains byte-identical when BCB is the source-native form.
- Existing passing targets may be reused only after their exact item/mode has gameplay evidence or a separately approved protected-control basis.
- `collision_free` may never be set by default. It requires an explicit calculated or gameplay-derived evidence record.

## 6. Workstream B: VanityBody

### 6.1 Inventory requirement

Inventory every SCO and Sindae wearable whose effective slot is `VanityBody`, including root-template-spawned variants that differ from named-stats underwear variants.

### 6.2 Confirmed correction anchors

The first correction package must address only these confirmed modes:

| Garment | Root UUID | Corrected mode(s) | Protected mode(s) |
|---|---|---|---|
| Wedding Body Suit | `50bf6831-84ff-42d1-aa18-a97dc3f96a6a` | Vanilla, SBBF | BCB |
| Satin Thong | `50ba99eb-d4d6-4a2a-99b5-4b5c13a4cb25` | Vanilla | SBBF, BCB |
| Serious Business Lady | `17ba99eb-d4d6-4a2a-99b5-4b5c13a4cb25` | Vanilla | SBBF, BCB |
| Sexy Catsuit | `82bf6831-84ff-42d1-aa18-a97dc3f96a6a` | Vanilla | SBBF, BCB |

The correction target is removal of the observed groin/genital breakthrough while preserving garment silhouette, materials, topology, skeleton, weights, vertex colors, tangents, and all non-target components.

### 6.3 Propagation rule

An anchor correction may propagate to another garment only when all of the following match:

- effective slot;
- source body form;
- topology/signature family;
- component contract;
- target body mode;
- observed defect mechanism.

Signature similarity alone may promote a sibling to `READY FOR TEST`; it may not promote it directly to an edited asset.

## 7. Workstream C: Complete SCO/Sindae coverage ledger

### 7.1 Completeness rule

Every discovered SCO and Sindae wearable source route must appear exactly once in the master ledger. Zero records may remain `UNCLASSIFIED` when the ledger is declared complete.

### 7.2 Required fields

- source module identity;
- root template and stats identities;
- effective equipment slot and inheritance evidence;
- garment family and topology/signature family;
- source VisualResource UUID/path;
- native body form;
- Vanilla/SBBF/BCB route existence;
- exact target VisualResource UUID/path for each route;
- target mesh provenance and hashes;
- gameplay result by mode;
- known defect and location;
- protected controls;
- package ownership;
- next action;
- evidence filenames.

### 7.3 Binding dispositions

Every record must end in one of:

- `ACCEPTED / PROTECT`
- `READY FOR TEST`
- `CONFIRMED DEFECT / CORRECT`
- `MISSING ROUTE / BUILD`
- `DEFERRED WITH CAUSE`
- `OUT OF SCOPE`

`READY FOR TEST` is not a gameplay pass. Static route or package validation is not visual acceptance.

### 7.4 Existing work reconciliation

The ledger must absorb and reconcile, rather than duplicate, all prior work for:

- SindaeSeven;
- Recluse and RecluseWave2;
- SoulVestAlt;
- Bard and Bard Dress;
- Butler;
- Oathbreaker;
- SCO Scalemail/Soul Vest faceting family;
- BCBScantily classes;
- Padded Armour/BG Watch deferrals;
- additional modded garments;
- previous accepted and rejected gameplay waves.

## 8. Mesh correction contract

### 8.1 Failing evidence first

Each corrected item/mode begins with a failing evidence record containing:

- source and current target hashes;
- exact source/target VRs and paths;
- screenshot or video evidence;
- visible defect location;
- body mode and character family;
- current route proof from `!cm_visdump` when available.

### 8.2 Static gates

For every corrected GR2:

- object/component count unchanged unless explicitly approved;
- vertex count and triangle topology unchanged for position-only edits;
- skeleton, weights, UVs, normals, tangents, vertex colors, and materials unchanged unless named in the correction contract;
- no new flipped triangles;
- no new zero-area triangles;
- no unacceptable area collapse;
- non-target components byte- or semantic-identical;
- fresh package extraction reproduces all expected files and hashes.

### 8.3 Clearance evidence

Generic body-shape deformation is insufficient evidence of genital or breast clearance. Each groin/genital correction requires either:

- a common-frame garment/body penetration calculation focused on the defect region; or
- matched gameplay evidence proving the corrected route and absence of the defect.

Static clearance evidence does not replace gameplay acceptance.

## 9. Package architecture

Use separate module identities and PAKs for:

1. VanityBody groin-fix TEST.
2. True-underwear TEST.
3. Class-specific SCO/Sindae correction waves when they cannot safely share dependencies or source ownership.

Packages must not share internal UUIDs or folders. A TEST PAK may remain physically installed while inactive, but exactly one mutually exclusive managed TEST provider may be active in a gameplay profile.

Every PAK must:

- declare all operational source and Runtime dependencies exactly;
- include only approved target assets and required route records;
- preserve protected payloads;
- have a source-to-stage-to-PAK-to-fresh-extraction manifest;
- include a test card and one-line spawn command for every item in its wave;
- distinguish packaging-ready from gameplay-proven.

## 10. Gameplay wave design

Gameplay waves are class-based but bounded:

- one class or one proven mechanism per wave;
- one supported character family unless a cross-family control is explicitly required;
- exact startup/profile gate before item grading;
- exact route proof before visual grading;
- Vanilla, SBBF, and BCB results recorded independently;
- front, side, and defect-region views;
- movement where cloth or pose dependence matters;
- save/reload once per package at a representative non-default route;
- protected-control checks;
- `PASS`, `FAIL`, `UNCLEAR`, or `INVALID PROFILE` only.

## 11. Deliverables

### 11.1 Ledgers

- `TRUE_UNDERWEAR_LEDGER.json`
- `VANITYBODY_LEDGER.json`
- `SCO_SINDAE_MASTER_GARMENT_LEDGER.json`
- human-readable Markdown summaries for each ledger

### 11.2 Candidates

- VanityBody groin-fix TEST PAK and test card
- true-underwear TEST PAK and test card
- additional class-specific candidates only after their ledger disposition and correction gates pass

### 11.3 Verification

- dependency-identity tests;
- slot-inheritance tests;
- exact manifest and fresh-extraction tests;
- topology/component-contract tests;
- protected-control tests;
- gameplay result tables remaining `NOT RUN` until Alan performs them.

## 12. Success criteria

The class-first milestone is complete only when:

1. Every discovered base/SCO/Sindae true-underwear item is classified and dispositioned.
2. Every discovered SCO/Sindae VanityBody item is classified and dispositioned.
3. Every discovered SCO/Sindae wearable route appears in the master ledger with no unclassified records.
4. Confirmed VanityBody anchor defects have new correction candidates that pass static gates.
5. The true-underwear package contains no VanityBody route.
6. Every package declares exact operational dependencies, including Runtime where its API is used.
7. No accepted/protected garment is changed without an explicit correction contract.
8. Every testable candidate has an isolated profile specification, spawn command, route expectations, and rollback record.
9. Gameplay success is claimed only from matching live route and visual evidence.

## 13. Current evidence carried forward

- Tiefling bodies and selected base-game armour are visually accepted by Alan, subject to the existing formal-profile limitations.
- Serious Business Lady has Vanilla groin clipping.
- Wedding Body Suit has Vanilla and SBBF genital clipping.
- Satin Thong has Vanilla genital clipping.
- Sexy Catsuit has slight Vanilla genital clipping.
- The prior Underwear TEST reused older ClothMorphBCB targets and did not contain new correction geometry.
- The prior Underwear TEST mixed VanityBody routes into an underwear-labelled package and omitted the Runtime from `meta.lsx` dependencies.
- RecluseWave2 remains unaccepted and has stale dependency-name metadata.
- Static/package evidence alone has not completed the SCO or Sindae garment classes.

## 14. Safety and live-state boundary

Classification, mesh generation, tests, and package construction occur only in Codex-owned workspace directories. No live PAK replacement or `modsettings.lsx` mutation occurs until the relevant candidate passes offline review and the user authorizes or requests the live test transition. BG3MM is not controlled or accessed through its UI.

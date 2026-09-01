# ClothMorph Terminal Exclusion Policy

**Date:** 2026-09-01  
**Status:** Approved continuation addendum, based on the user's direction to fix every outstanding element or declare it unfixable and excluded  
**Parent specification:** `C:\Claude Projects\BG3 Mods\ChatGPT Work Files\ClothMorph_Shippable_Release_Program_20260830\docs\superpowers\specs\2026-08-30-clothmorph-shippable-release-program-design.md`  
**Scope:** Release-ledger terminal dispositions only; no live installation, save cleanup, Runtime cleanup API, protected-route mutation, or gameplay acceptance is authorized by this addendum

## TL/DR

An unresolved record may stop blocking the revised release only by becoming a protected/accepted shipped behavior, a verified shipped refit, or an explicit `OUT_OF_SCOPE_WITH_PROOF` exclusion backed by an append-only exclusion event. An exclusion is not a synonym for deferred work: it requires exact identity, a permitted exclusion reason, complete evidence hashes, proof that protected consumers are unaffected, and a documented exhaustion or hard-impossibility basis.

The accepted Tiefling provider is not eligible for exclusion or regrading. It remains a byte-identical user-approved PASS and must be included unchanged in the eventual whole-mod test bundle.

## 1. Binding terminal states

The release audit recognizes these terminal outcomes:

- `ACCEPTED_PROTECTED`
- `SOURCE_NATIVE_PROTECTED` when the requested release behavior is exact source-native passthrough and the evidence is protected
- `SHIPPED_NATIVE_PASSTHROUGH`
- `SHIPPED_REFIT`
- `OUT_OF_SCOPE_WITH_PROOF` only when a valid exclusion event is attached and `release_blocking=false`

The following remain nonterminal:

- `PACKAGE_ONLY_PROTECTED`
- `READY_FOR_OFFLINE_CORRECTION`
- `OFFLINE_CANDIDATE_PASS`
- `PACKAGE_READY_GAMEPLAY_UNASSESSED`
- `BLOCKED_WITH_CAUSE`
- `DEFERRED_WITH_CAUSE`
- any record with an invalid, missing, superseded, or contradictory exclusion event

## 2. Allowed exclusion reasons

Every exclusion event uses exactly one primary reason:

- `SOURCE_ABSENT_EXACT_PROFILE`: the exact hash-pinned source version does not contain the requested route or asset.
- `NO_RELEASE_PERMISSION`: preserved permission/license evidence prohibits the required derivative or distribution.
- `NON_WEARABLE_OR_UNSUPPORTED_BODY_TUPLE`: the exact route is not a garment in the declared revised-mod scope or belongs to a body/race/slot tuple the release does not advertise.
- `PROTECTED_NATIVE_ONLY`: the requested behavior is already an exact protected source-native route and a new target would duplicate or endanger it.
- `NO_SAFE_GEOMETRY_AVAILABLE`: all declared safe automated architectures for the exact component contract failed fixed geometry gates, and no candidate can be produced without entering a separately approved manual-remesh/source-replacement project.
- `UNRESOLVED_SOURCE_CONTRACT_AFTER_EXHAUSTIVE_AUDIT`: every retained exact source, dependency, VisualBank, RootTemplate, Stats, and provider record was searched, but the canonical route cannot be reconstructed without inference.
- `INCOMPATIBLE_MUTUALLY_EXCLUSIVE_PROFILE`: the route belongs only to a profile explicitly forbidden by the selected release family and is covered by the alternate profile's separate artifact.

Display names, filenames, screenshots, similarity, missing time, missing implementation, or a single failed algorithm are never exclusion reasons.

## 3. Exclusion event contract

Each event is append-only and contains:

```json
{
  "schema": "clothmorph.terminal-exclusion",
  "schema_version": 1,
  "event_id": "EXCLUSION_<UPPERCASE_SHA256>",
  "record_id": "LEDGER_<UPPERCASE_SHA256>",
  "identity_sha256": "64 uppercase hexadecimal characters",
  "source_profile_id": "exact profile id",
  "mode": "vanilla | sbbf | bcb | external | source",
  "reason": "one allowed exclusion reason",
  "scope_statement": "exact behavior removed from the advertised release",
  "attempted_architectures": [],
  "fixed_acceptance_gates": {},
  "evidence": [
    {
      "path": "retained offline evidence path",
      "sha256": "64 uppercase hexadecimal characters",
      "claim": "single bounded fact proven by this artifact"
    }
  ],
  "protected_impact": {
    "registry_ids": [],
    "shared_consumers": [],
    "forbidden_targets": [],
    "result": "NO_PROTECTED_MUTATION"
  },
  "next_project_if_reopened": "separately approved architecture or evidence requirement",
  "approved_by": "Alan",
  "approved_reason": "fix every outstanding element or declare it unfixable and excluded",
  "created_utc": "ISO-8601 timestamp"
}
```

The event digest binds the canonical JSON excluding `event_id`; `event_id` is `EXCLUSION_` plus that digest.

## 4. Geometry exhaustion rule

`NO_SAFE_GEOMETRY_AVAILABLE` requires one of these proof paths:

### 4.1 Hard contract impossibility

- required source geometry is absent from the exact profile; or
- the only candidate would change a protected object/component/material/body boundary forbidden by the release contract; or
- the required garment-only boundary cannot be established without modifying embedded body data, after exact component comparison against every retained source/target candidate.

### 4.2 Bounded architecture exhaustion

- at least three materially distinct safe architectures have been tested, or the parent findings already establish three failed architectures and the declared final materially different architecture is tested;
- every architecture uses the same predeclared nontriviality, topology, component, material, skin, clearance, silhouette, and deterministic-readback gates;
- failures are recorded per component and do not rely on subjective labels alone;
- parameter tuning within one architecture does not count as a distinct architecture;
- no passing component is emitted when the route contract requires an atomic multi-component pair; and
- the final report states `UNFIXABLE_WITH_AVAILABLE_SAFE_TOOLING`, not mathematically impossible.

Manual sculpting, manual landmark authoring, topology-changing remesh, source replacement, or protected-object substitution is a separate architecture. If it is not available within the approved offline toolchain, the exclusion event names it as the only admissible reopening project.

## 5. Source/route exhaustion rule

`UNRESOLVED_SOURCE_CONTRACT_AFTER_EXHAUSTIVE_AUDIT` requires:

- exact source PAK/profile identity and retained hash;
- complete inventory of RootTemplates, named Stats, inheritance, VisualBanks, ordered components, and provider maps;
- exact searches for every known UUID/path/hash alias;
- a zero-result or contradictory-result report with input manifests;
- independent anti-omission verification; and
- no unresolved retained evidence file that could still supply the identity.

An unavailable live mod file does not qualify if a retained source archive exists. A missing source profile remains blocking until the profile audit itself reaches a terminal exclusion.

## 6. Permission exclusion rule

`NO_RELEASE_PERMISSION` requires preserved exact permission/license text or an independently verifiable license artifact, date, evidence hash, credit, derivative scope, redistribution scope, and the exact source version. Summary prose or inferred author intent cannot close permission.

A `private_test_only` profile may produce an internal TEST PAK when its evidence permits that use, but it remains excluded from public release output until `release_cleared`.

## 7. Protected and accepted controls

- The v1 protected registry and manifest remain immutable.
- An exclusion event cannot target an accepted route, user-accepted residual, or protected source-native control for deletion or mutation.
- A new unaccepted consumer sharing a protected asset receives a new provider-owned target or is excluded; the protected file/path/VR/hash remains unchanged.
- The byte-identical Tiefling PAK `ClothMorphTieflingBT1_TEST.pak`, UUID `b57bab2c-5679-5445-8fee-ca8c282990a5`, SHA-256 `01E96CF236607F5A4B9E4DD2D7A6BE2CA8A9013456706000DC3248543390F141`, is a mandatory whole-mod bundle component and cannot receive an exclusion event.

## 8. Audit behavior

The completion audit treats `OUT_OF_SCOPE_WITH_PROOF` as terminal only when:

- the exclusion event validates;
- event `record_id` and `identity_sha256` match the ledger record;
- every evidence file exists and matches its registered hash;
- the event is the newest non-revoked event for that record/mode;
- protected impact is `NO_PROTECTED_MUTATION`;
- the record's advertised-scope flag is false for the excluded behavior;
- `release_blocking=false`; and
- no packaged provider route still claims the excluded behavior.

Invalid exclusions remain in `in_scope_nonterminal` and produce stable audit codes. The audit emits exact sets for excluded record IDs and exclusion-validation failures.

## 9. Packaging and documentation

- Excluded routes are absent from provider maps and PAK payloads.
- The whole-mod test card lists exclusions in a dedicated appendix with record ID, reason, evidence, and reopening condition.
- No exclusion is represented as gameplay PASS.
- The release README states the exact profile/body/mode scope after exclusions.
- Internal TEST PAKs may exist for nonterminal candidates; their existence does not terminally close the route.

## 10. Completion consequence

The revised release program continues until every record is either:

1. protected/accepted and preserved;
2. fixed, package-verified, and accepted under the parent specification; or
3. excluded by a valid event under this policy.

The master ledger, provider manifests, PAK contents, test card, and public documentation must agree on the same final set.

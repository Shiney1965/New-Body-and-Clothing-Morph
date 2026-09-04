# ClothMorph Release Master Ledger Public Checkpoint - 2026-09-03

## TL/DR

The current hash-locked offline evidence generates deterministically into `3,172` observations and `3,170` master-ledger records. The generated audit reports `source_complete=false` and `release_complete=false`: `20` of `23` required source profiles are now section-7.1-complete via freeze-census + independent permission joins plus the retained base-game aggregate capture bind (`BASE_GAME_SOURCE_PROFILE_UNRESOLVED` closed from clothmorph-runtime14 `base_game_profile_20260902` digests; nineteen mod freeze-bound census candidates are complete — the prior thirteen including SCO `73928ffc` with Alan's exact Nexus 2617 permissions-tab quote and BCB core trio BCBPak `1d24059d` / BCBUniqueTav `28c82588` / BCBScantily `75934b95`, plus Imports/NightreignStylePak `096665c7` (SindaeImportedOutfits.pak sha `F91C4F78…`) and SindaeTexturePak `873d1b73` (sha `33BE5016…`) paired freeze-promote from census `core_source_freeze_20260902_retry1` pak digests; SindaeTexturePak is dependency-only / paired operational dep, not a garment-source twin (documented in local/SINDAE_TEXTUREPAK_DEPENDENCY_ONLY.md); BCBPak vs BCBUniqueTav remains body-path XOR / mutually exclusive install, not additive dual-body; all garments in each BCB pak are in-scope; three required identities remain freeze-missing — Tiefling `b57bab2c` (never-exclude; later TEST/contract), Recluse Wave2 TEST `e204398d`, and Underwear TEST `fb6466cc` stay out of this slice; ClothMorph Runtime/BCB/SCO/External providers closed this bound), seven prior-evidence inputs are not yet joined to concrete records, `ledger_without_source=0`, and all `3,170` records remain release-blocking/nonterminal. Empty-scope Gloomstalker permission placeholders are no longer emitted as invented `UNKNOWN_PERMISSION_SCOPE` meshes; Recluse package evidence remains independently inventoried as a source observation; Soul Vest/Alt and Bard findings join onto matching coverage garment records; unmatched Padded/BG Watch findings remain an inventoried provisional named-target row. There are currently no approved exclusion events: `excluded_modes_with_proof=0`, `excluded_with_proof=0`, `exclusion_validation_failures=0`, `exclusion_history_failures=0`, and `excluded_but_packaged=0`. Every record's four-mode scope remains advertised/nonterminal and every per-mode exclusion attachment is `null`. The `2026-09-03` ClothMorph provider freeze-promote generation (Runtime/BCB/SCO/External; roles runtime/provider; public author SerpentineShel; documented in local/CLOTHMORPH_PROVIDER_ROLES.md) repeated the real generator twice and reproduced the artifact hashes and counts below.

The protected registry reconciles exactly `32` immutable controls: `25` `GAMEPLAY_PASS`, `1` `USER_ACCEPTED_RESIDUAL`, `2` `PROTECTED_SOURCE_NATIVE`, and `4` `PROTECTED_SOURCE_NATIVE_PACKAGE_ONLY`. The four package-only Recluse controls remain gameplay-unproven and were not promoted.

## Generated current identities

These artifacts are local evidence outputs under ignored `workstreams/release_master_ledger/local/generated/`; they are not committed release authorities.

| Artifact | Bytes | SHA-256 |
|---|---:|---|
| `REMAINING_TARGET_MASTER_LEDGER.json` | `25,861,142` | `7376046639C3A97FD00B7F9CF4911AD3BA1A447043B26733C951BECF0C8D7E60` |
| `REMAINING_TARGET_MASTER_LEDGER.md` | `577` | `D297B7B4C892BE74BF8FF23C36062AFED37CFD7C7C563CB39D8A568F567AC54E` |
| `RELEASE_LEDGER_COMPLETENESS_AUDIT.json` | `792,945` | `E536D992E72A733C6C7544E211549EEB5B75613F7768EC6F282871E84576490D` |
| `EVIDENCE_INPUT_MANIFEST.json` | `8,265` | `55D08027E66AB7E2A9DBB4875B7D7F1B99A2A9ECF49F642A9F61BCBBE8668D47` |

Two consecutive `2026-09-03` ClothMorph provider freeze-promote CLI generations produced these same four hashes.

## Current ledger and audit facts

- Registered inputs: `18`.
- Source observations: `3,172`.
- Independently inventoried concrete source observations: `3,172`.
- Emitted records: `3,170`.
- Release-blocking records: `3,170`.
- `UNCLASSIFIED`: `0`.
- Required source profiles complete: `false`.
- `source_complete`: `false`.
- `release_complete`: `false`.
- `missing_from_ledger`: `0`.
- `duplicate_identity`: `0`.
- `unreferenced_prior_evidence`: `7`.
- `packaged_without_ledger`: `0`.
- `ledger_without_source`: `0`.
- `in_scope_nonterminal`: `3,170`.
- `excluded_modes_with_proof`: `0`.
- `excluded_with_proof`: `0`.
- `exclusion_validation_failures`: `0`.
- `exclusion_history_failures`: `0`.
- `excluded_but_packaged`: `0`.
- Required source profiles: `23`.
- Complete source profiles: `20`.
- Missing source profiles: `3` (BASE_GAME closed; BCB core trio closed; Imports+SindaeTexturePak closed; ClothMorph Runtime/BCB/SCO/External providers closed). Freeze-bound identities: `20` (`19` mod freeze candidates + `BASE_GAME_SOURCE_PROFILE_UNRESOLVED`; `20` complete / `0` census-incomplete). Freeze-missing required identities: `3` (Tiefling never-exclude + Recluse/Underwear TEST).

The bounded primary channels remain `2,534` coverage records, `68` true-underwear records, and `271` VanityBody records. All eight configured supporting inputs have zero observation/record count, so they do not inflate the ledger.

The protected hash manifest is reconciled one-to-one by registry ID/path/bytes/SHA/consumer metadata and attached as provenance to all `32` protected records without opening any protected payload. The other seven supporting inputs remain truthfully listed in `unreferenced_prior_evidence` until concrete record-level joins exist. Census candidates are independently inventoried for required/freeze-bound profile identities but are not attached as per-record evidence paths. All nineteen mod freeze-bound candidates become section-7.1-complete when independently bound permission evidence fills admissible contracts (SCO via Alan's exact Nexus 2617 permissions-tab quote; BCB core trio via Alan's 2026-07-11 Nexus 2351 review / Sindae required-dependency grant; BCBPak vs BCBUniqueTav body-path XOR documented in local/BCB_PAK_UNIQUE_TAV_BODY_PATH_XOR.md; Imports `096665c7` + SindaeTexturePak `873d1b73` paired freeze-promote with TexturePak dependency-only semantics documented in local/SINDAE_TEXTUREPAK_DEPENDENCY_ONLY.md; ClothMorph Runtime `20aca985` / BCB `78f1571f` / SCO provider `0d73fe2f` / External `fdb658be` first-party freeze-promote with roles runtime/provider documented in local/CLOTHMORPH_PROVIDER_ROLES.md (public author SerpentineShel; not garment-source twins); citation-only SCO bind aborted); their census `release_profile_complete` remains false. `BASE_GAME_SOURCE_PROFILE_UNRESOLVED` is freeze-bound and section-7.1-complete from retained `base_game_profile_20260902` capture digests (Shared.pak `9D63D634…`, content manifest `08394D7A…`, EquipmentRaces `FC66EDC4…`, top-level package hash manifest `048FB0EB…`, exe `E899C67C…`) via aggregate census `release_profile_complete=true` without inventing a Shared package freeze identity. `packaged_without_ledger=0` and `ledger_without_source=0` are earned against independently inventoried package observation ownership ID `PACKAGE_SHA256:A4BB716CB70C8046FE87ECB94A8D081563D953AD1E07BA1F521B01765768E345`, present on the Recluse record with module UUID `096665c7-75aa-4747-9548-6ccafba985c8` and version `36028797018963968`; Imports freeze-promotion is now closed for source-profile completeness; the Recluse record remains release-blocking and gameplay-unassessed. Hard named garments remain in-scope outstanding (`excluded_with_proof=0`).

## Exact current input boundary

| Input ID | Bytes | SHA-256 |
|---|---:|---|
| `protected_registry_v1` | `78,623` | `7AFA8A00E8D491F419A32851D316C74C4E283DA4E0E4C2DBFB1E968FF9119924` |
| `protected_hash_manifest_v1` | `14,662` | `56DD4FB852166D587FDAC0B35746CA222CA935B42F893FBA0DAE7F1EFB568F8A` |
| `coverage_master_registry_scoped` | `6,685,710` | `D6ED8962D4B2FE48BA60BFAA63D49E2350381F3300D5D0F79F7502FACE1813CC` |
| `coverage_raw_registry_scoped` | `6,024,566` | `8A50BEC3E670FB21F5548574573560BFAA4A5C2CCA64B64B6B325F0A141F86C2` |
| `true_underwear_ledger_v2` | `84,355` | `874E33321DDC9B3A88329458B069FE1F324D05ED5189B361F7164AD9C664F602` |
| `true_underwear_route_audit` | `52,964` | `6E4576583898312AD9FF58A39DA4D280C7281510340D6EF186577C16ED1ACA3E` |
| `vanitybody_ledger_bcbpak` | `178,923` | `2ADDF9D42DDA0A69FF8EE234EBD9E18BF196C26AA6A9F4124A84DBC1110D4A92` |
| `vanitybody_route_protection` | `6,814` | `5CFDCFA53A2B0747AADC1FC996C4FA4B9A41919D34E63EEB8371BC5130A23E8B` |
| `bcbscantily_class_ledger` | `24,261` | `266575498CFA9A6130A693DFBB90B3B30A57945CA499C401BF1F9D3595BBC1A4` |
| `bcbscantily_item_contracts` | `850,968` | `2914AA90144E9AF8529993A22580F4391080743C8061DA44DD2F5211BD1BBBBC` |
| `external_permission_manifest_v1` | `152,101` | `56A442C849F9BEF04AF6471B1461DF36A9AAAB503F46C7BABFC5417F26DDD3D6` |
| `recluse_provider_contract_v2` | `1,458` | `C56B0208C09D04531258BFCC01BF7319C05EC47C36FCA750C84428A4CEC0DA01` |
| `soul_vest_alt_decision` | `1,326` | `2FE915214CFAAB8953A923EACA47FCF98803ED8A37BAA257D03DF5FD78E67E23` |
| `padded_findings` | `15,507` | `CDD5CBAE21FC88BABAFC1893F5D7BA1B4B5C34FDECDAD64671D45B5EEC96ADA8` |
| `bard_findings` | `9,180` | `2C7324F0198115906C49B3584F95D780A209B5FBEE1B42A448CFC0044F2262FB` |
| `source_profile_inventory` | `20,044` | `9CB045CD9850867FEDFA9A98587096C953360F47D81BD074B1A5E8C050AE5E00` |
| `source_profile_census_candidates` | `52,471` | `DDC15FEDD09BF9DE894667DA24BE6605F08F33CE6CDB30402116B0AAF00C44E4` |
| `base_game_aggregate_census` | `2,604` | `4E44EE73BCD628856EFBAD2964197285839ACDF0E2EB7B116CD345117340E806` |

Every input is hashed before parsing. The exclusion history is restricted to the exact canonical ignored path `workstreams/release_master_ledger/local/exclusion_events`; it currently contains zero event files. Paths merely named inside retained JSON— including live/AppData source-PAK, profile, log, and mod paths—were not dereferenced.

## Release-blocking boundary

The generated ledger contains `12` stable blocker codes. Its numeric `schema_version` is `1`, and the full generated envelope plus every emitted record passes the standard-library generated-document validator. Terminal exclusion is closed and per mode: one event cannot close a four-mode record, excluded modes must carry zero provider/target/payload/provenance/package claims, and unmatched or orphan history is emitted under stable audit codes. Each blocker entry includes evidence pointers, an owner, a next admissible action, affected record IDs, and a `release_blocking` flag.

This checkpoint is offline evidence only. It does not prove gameplay, fresh package/profile construction, advertised combined-profile behavior, installer/restore behavior, save safety, or release readiness.

# ClothMorph Release Master Ledger Public Checkpoint — 2026-09-01

## TL/DR

The current hash-locked offline evidence generates deterministically into `3,173` observations and `3,173` master-ledger records. The generated audit reports `source_complete=false` and `release_complete=false`: required source-profile completeness is not established, all `3,173` records remain in `in_scope_nonterminal`, all are release-blocking, and later package/gameplay/installer gates remain unproved.

The protected registry reconciles exactly `32` immutable controls: `25` `GAMEPLAY_PASS`, `1` `USER_ACCEPTED_RESIDUAL`, `2` `PROTECTED_SOURCE_NATIVE`, and `4` `PROTECTED_SOURCE_NATIVE_PACKAGE_ONLY`. The four package-only Recluse controls remain gameplay-unproven and were not promoted.

## Generated current identities

These artifacts are local evidence outputs under ignored `workstreams/release_master_ledger/local/generated/`; they are not committed release authorities.

| Artifact | Bytes | SHA-256 |
|---|---:|---|
| `REMAINING_TARGET_MASTER_LEDGER.json` | `24,044,344` | `B7BF69AEF819558160AF246F6EB319DEF312EF5D5E340455480A8C32C45371B7` |
| `REMAINING_TARGET_MASTER_LEDGER.md` | `478` | `5EC08BAEDD4DCA6A66FB513FE0A6EEE19EDACFD7D992D45CC599561BCD76A9A9` |
| `RELEASE_LEDGER_COMPLETENESS_AUDIT.json` | `251,449` | `6698FA0AAC1EA8935ACB437C928F9EAAC2DED34A38E75B62329DC1C6EA09B6F3` |
| `EVIDENCE_INPUT_MANIFEST.json` | `7,057` | `E3E65616A94D4B9AB961CA4AF3013721878232548F3571CE018F97F67DF68631` |

Two consecutive CLI generations produced these same four hashes.

## Current ledger and audit facts

- Registered inputs: `16`.
- Source observations: `3,173`.
- Emitted records: `3,173`.
- Release-blocking records: `3,173`.
- `UNCLASSIFIED`: `0`.
- Required source profiles complete: `false`.
- `source_complete`: `false`.
- `release_complete`: `false`.
- `missing_from_ledger`: `0`.
- `duplicate_identity`: `0`.
- `unreferenced_prior_evidence`: `0`.
- `packaged_without_ledger`: `0`.
- `ledger_without_source`: `0`.
- `in_scope_nonterminal`: `3,173`.

The bounded primary channels remain `2,534` coverage records, `68` true-underwear records, and `271` VanityBody records. Supporting inventories, route audits, protection evidence, and class/source-profile manifests are pinned in the evidence manifest but are not promoted into additional garment observations.

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
| `external_permission_manifest_v1` | `118,574` | `C02DFB56B6F246C7902F31EA371405763F1BB555CA5CE016CB06A31895EBA908` |
| `recluse_provider_contract_v2` | `1,458` | `C56B0208C09D04531258BFCC01BF7319C05EC47C36FCA750C84428A4CEC0DA01` |
| `soul_vest_alt_decision` | `1,326` | `2FE915214CFAAB8953A923EACA47FCF98803ED8A37BAA257D03DF5FD78E67E23` |
| `padded_findings` | `15,507` | `CDD5CBAE21FC88BABAFC1893F5D7BA1B4B5C34FDECDAD64671D45B5EEC96ADA8` |
| `bard_findings` | `9,180` | `2C7324F0198115906C49B3584F95D780A209B5FBEE1B42A448CFC0044F2262FB` |
| `source_profile_inventory` | `20,044` | `9CB045CD9850867FEDFA9A98587096C953360F47D81BD074B1A5E8C050AE5E00` |

Every input is hashed before parsing. Paths merely named inside retained JSON— including live/AppData source-PAK, profile, log, and mod paths—were not dereferenced.

## Release-blocking boundary

The generated ledger contains `12` stable blocker codes. Each generated blocker entry includes evidence pointers, an owner, a next admissible action, affected record IDs, and a `release_blocking` flag.

This checkpoint is offline evidence only. It does not prove gameplay, fresh package/profile construction, advertised combined-profile behavior, installer/restore behavior, save safety, or release readiness.

# Public Coverage-Ledger Checkpoint

## What this public workstream provides

This directory provides portable Python algorithms and fully synthetic unit fixtures for:

- representing a concrete garment-route identity;
- resolving a declared slot-inheritance chain;
- reconciling exact-identity evidence without allowing root-only annotations to control a route;
- fail-closing incomplete route contracts; and
- grouping already-ready records into bounded, dependency-compatible card data.

The portable tests prove those fixture-backed behaviors only. They do not read a game installation, an extracted mod tree, a PAK, a mesh, a local registry, or gameplay evidence.

## Deliberately omitted local material

Local source registries, prior-evidence registrations, generated ledgers, generated cards, archived cards, and implementation reports are ignored. Their paths, counts, hashes, identities, and evidence are intentionally not published here. The canonical local configuration is `local/local_configuration.json`, created from [local_configuration.example.json](local_configuration.example.json), and an operator must explicitly set `COVERAGE_LEDGER_LOCAL_CONFIG` to that file to run a local generation integration.

The configured generated-output paths must resolve inside this workstream's ignored `local/` directory. Source-input paths may point to separately retained local material, but they are not copied into public output.

When that configuration is absent, local generation is unavailable by design and integration tests skip with that reason. This is not a failed portable test and it is not evidence about any source inventory.

## Limits of this checkpoint

This checkpoint makes **no** claim of global garment coverage, complete source coverage, source authority, package readiness, PAK contents, mesh provenance, route selection, visual fit, collision clearance, save/load behavior, or gameplay acceptance. It does not distribute third-party assets or source-derived identifiers.

Any future coverage or gameplay conclusion requires separately reviewed local source and live-test evidence.

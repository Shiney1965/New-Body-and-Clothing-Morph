# Public Checkpoint: True Underwear Classification

This public subset proves the offline, fail-closed mechanics used to classify
one concrete creation path at a time.  The committed fixture tests verify
stats `using` inheritance, explicit cycle and missing-parent failures,
separation of named-stats and root-template paths when their slots disagree,
and rejection of `VanityBody` from the true-underwear route-audit input.

It does not prove complete underwear coverage.  No public ledger count,
source VisualResource join, native-body determination, target route, mesh hash,
topology check, protected BCB passthrough, package dependency result, PAK, or
gameplay result is present or claimed here.

## Local-only inputs and integration evidence

Source archives, extracted game/mod files, generated ledgers, manifests,
reports, and workstation helpers remain local and are intentionally omitted.
`tests/test_real_sources.py` is an opt-in integration suite: it runs only when
both `TRUE_UNDERWEAR_SOURCE_CONFIG` and `TRUE_UNDERWEAR_EVIDENCE_DIR` name
local inputs.  It is excluded from the portable command below.

Classification is pure: rejection rows are returned with records and cannot
write a caller-selected path. Only the canonical local ledger writer persists
the rejection JSON under `local/generated/` after boundary validation.

To run a local inventory operation, copy `source_config.example.json` to
`local/source_config.json` and replace only its relative placeholder paths
with your own offline inputs. The configuration path and generated results are
deliberately fixed to the ignored `local/` boundary; source-input paths inside
that configuration may use relative traversals to retained local inputs. From
the `workstreams` directory, run:

    python -m true_underwear.generate_ledger

The example configuration is deliberately nonfunctional.  It contains no game
or third-party extracted asset content and makes no claim about availability or
coverage.

## Portable verification

Run only fixture-backed public tests:

    python -m pytest -m "not integration" true_underwear/tests -v

Passing this command proves the tested classification and configuration
behaviors only. A route is merely `READY FOR TEST` when each body-mode route
has a complete target VR/path/SHA-256 contract and the explicit
`PROVENANCE_VALIDATED` status; it is still not evidence of PAK, mesh, visual,
save/load, or gameplay readiness.

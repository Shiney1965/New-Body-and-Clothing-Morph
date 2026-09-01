from pathlib import Path

from workstreams.release_master_ledger.adapters import (
    adapt_bcbscantily, adapt_coverage, adapt_named_target, adapt_one_protected,
    adapt_package_evidence, adapt_permission_manifest, adapt_true_underwear,
)
from workstreams.release_master_ledger.configuration import VerifiedInput
from workstreams.release_master_ledger.reconcile import reconcile_observations
from workstreams.release_master_ledger.validation import validate_record


def verified(kind):
    return VerifiedInput(
        input_id=f"synthetic-{kind.lower()}", kind=kind, path=Path("synthetic.json"),
        bytes=1, expected_sha256="A" * 64, actual_sha256="A" * 64,
    )


def test_adapter_observations_reconcile_to_validator_complete_records():
    observations = [
        adapt_one_protected({"status": "GAMEPLAY_PASS"}, verified("PROTECTED_REGISTRY")),
        adapt_coverage([{"disposition": "OFFLINE CANDIDATE PASS"}], verified("COVERAGE"))[0],
        adapt_true_underwear([{}], verified("TRUE_UNDERWEAR"))[0],
        adapt_bcbscantily([{}], verified("BCBSCANTILY"))[0],
        adapt_permission_manifest({"scope_resolved": ["synthetic.gr2"]}, verified("PERMISSION"))[0],
        adapt_package_evidence([{}], verified("PACKAGE"))[0],
        adapt_named_target([{"display_name": "Synthetic"}], verified("NAMED_TARGET"))[0],
    ]

    result = reconcile_observations(observations)

    assert len(result.records) == len(observations)
    assert all(validate_record(record.to_dict()) == [] for record in result.records)

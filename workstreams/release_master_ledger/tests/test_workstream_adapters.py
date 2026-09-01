import hashlib
import json
from pathlib import Path

from workstreams.release_master_ledger.adapters import (
    adapt_bcbscantily,
    adapt_coverage,
    adapt_named_target,
    adapt_package_evidence,
    adapt_true_underwear,
    adapt_vanitybody,
)
from workstreams.release_master_ledger.configuration import VerifiedInput


FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def verified_fixture(name, kind):
    path = FIXTURES / name
    content = path.read_bytes()
    digest = hashlib.sha256(content).hexdigest().upper()
    return VerifiedInput(
        input_id=f"fixture-{kind.lower()}", kind=kind, path=path, bytes=len(content),
        expected_sha256=digest, actual_sha256=digest,
    )


VERIFIED_COVERAGE = verified_fixture("coverage_records.json", "COVERAGE")
VERIFIED_UNDERWEAR = verified_fixture("underwear_records.json", "TRUE_UNDERWEAR")
VERIFIED_VANITY = verified_fixture("vanity_records.json", "VANITYBODY")


def underwear_fixture(**overrides):
    record = load_fixture("underwear_records.json")[0]
    record.update(overrides)
    return record


def test_coverage_maps_offline_and_package_states_without_gameplay_promotion():
    observations = adapt_coverage(load_fixture("coverage_records.json"), VERIFIED_COVERAGE)

    assert observations[0].disposition == "OFFLINE_CANDIDATE_PASS"
    assert observations[0].evidence_status == "GAMEPLAY_UNASSESSED"
    assert observations[1].disposition == "PACKAGE_READY_GAMEPLAY_UNASSESSED"
    assert observations[1].release_blocking is True
    assert observations[1].evidence_status == "GAMEPLAY_UNASSESSED_PACKAGE_ONLY"


def test_underwear_missing_route_remains_blocking():
    observation = adapt_true_underwear(
        [underwear_fixture(disposition="MISSING ROUTE / BUILD")], VERIFIED_UNDERWEAR
    )[0]

    assert observation.disposition == "BLOCKED_WITH_CAUSE"
    assert "TARGET_ROUTE_UNRESOLVED" in observation.blocker_codes


def test_vanity_ready_for_test_is_deferred_without_section_9_contract():
    observation = adapt_vanitybody(load_fixture("vanity_records.json")[:1], VERIFIED_VANITY)[0]

    assert observation.disposition == "DEFERRED_WITH_CAUSE"
    assert "SECTION_9_CONTRACT_UNRESOLVED" in observation.blocker_codes


def test_bcbscantily_without_visual_resource_or_component_contract_remains_blocking():
    observation = adapt_bcbscantily(load_fixture("vanity_records.json")[1:], VERIFIED_VANITY)[0]

    assert observation.disposition == "BLOCKED_WITH_CAUSE"
    assert "SOURCE_VR_UNRESOLVED" in observation.blocker_codes
    assert "COMPONENT_CONTRACT_UNRESOLVED" in observation.blocker_codes


def test_package_evidence_never_reports_gameplay_acceptance():
    observation = adapt_package_evidence(
        [{"observation_id": "fixture-package-1", "package_status": "PACKAGE_PASS"}],
        VERIFIED_COVERAGE,
    )[0]

    assert observation.disposition == "PACKAGE_READY_GAMEPLAY_UNASSESSED"
    assert observation.evidence_status == "GAMEPLAY_UNASSESSED_PACKAGE_ONLY"
    assert observation.release_blocking is True


def test_named_target_display_name_is_not_an_identity_or_route():
    observation = adapt_named_target(
        [{"display_name": "A very convincing garment name"}], VERIFIED_COVERAGE
    )[0]

    assert observation.classification["effective_slot"] == "AMBIGUOUS_SLOT"
    assert "NAMED_TARGET_UNRESOLVED" in observation.blocker_codes

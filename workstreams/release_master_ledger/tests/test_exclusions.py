"""Tests for fail-closed terminal-exclusion events.

Each test protects a policy boundary: an invalid, ambiguous, or revoked event
must not become the current exclusion for a ledger route.
"""

from copy import deepcopy

import pytest

from workstreams.release_master_ledger.exclusions import (
    ExclusionSelection,
    canonical_exclusion_payload,
    exclusion_event_id,
    select_current_exclusion,
    validate_exclusion_event,
)


RECORD_ID = "LEDGER_" + "A" * 64
IDENTITY_SHA256 = "B" * 64
EVIDENCE_SHA256 = "C" * 64
PROFILE_ID = "SYNTHETIC_PROFILE"
TIEFLING_PAK_SHA256 = "01E96CF236607F5A4B9E4DD2D7A6BE2CA8A9013456706000DC3248543390F141"


def ledger_record(**overrides):
    record = {
        "record_id": RECORD_ID,
        "identity_sha256": IDENTITY_SHA256,
        "source_module": {
            "folder": PROFILE_ID,
            "pak": "Synthetic.pak",
            "uuid": "11111111-1111-1111-1111-111111111111",
            "pak_sha256": "D" * 64,
            "profile_digest": "E" * 64,
        },
        "protected_relations": {
            "registry_ids": [],
            "protected_consumers": [],
            "forbidden_targets": [],
        },
    }
    record.update(overrides)
    return record


def exclusion_fixture(**overrides):
    event = {
        "schema": "clothmorph.terminal-exclusion",
        "schema_version": 1,
        "record_id": RECORD_ID,
        "identity_sha256": IDENTITY_SHA256,
        "source_profile_id": PROFILE_ID,
        "mode": "sbbf",
        "reason": "SOURCE_ABSENT_EXACT_PROFILE",
        "scope_statement": "Exclude only the exact synthetic SBBF route.",
        "attempted_architectures": [],
        "fixed_acceptance_gates": {},
        "evidence": [{
            "path": "evidence/synthetic-source-audit.json",
            "sha256": EVIDENCE_SHA256,
            "claim": "SOURCE_ABSENT_EXACT_PROFILE: exact profile route absent.",
        }],
        "protected_impact": {
            "registry_ids": [],
            "shared_consumers": [],
            "forbidden_targets": [],
            "result": "NO_PROTECTED_MUTATION",
        },
        "next_project_if_reopened": "Recover an exact source profile.",
        "approved_by": "Alan",
        "approved_reason": "fix every outstanding element or declare it unfixable and excluded",
        "created_utc": "2026-09-01T12:00:00Z",
    }
    event.update(overrides)
    return event


def signed_event(**overrides):
    event = exclusion_fixture(**overrides)
    event["event_id"] = exclusion_event_id(event)
    return event


def test_canonical_payload_is_sorted_json_without_the_event_id():
    event = exclusion_fixture(event_id="EXCLUSION_" + "F" * 64)

    assert canonical_exclusion_payload(event) == (
        '{"approved_by":"Alan","approved_reason":"fix every outstanding element or declare it unfixable and excluded",'
        '"attempted_architectures":[],"created_utc":"2026-09-01T12:00:00Z",'
        '"evidence":[{"claim":"SOURCE_ABSENT_EXACT_PROFILE: exact profile route absent.",'
        '"path":"evidence/synthetic-source-audit.json","sha256":"' + EVIDENCE_SHA256 + '"}],'
        '"fixed_acceptance_gates":{},"identity_sha256":"' + IDENTITY_SHA256 + '",'
        '"mode":"sbbf","next_project_if_reopened":"Recover an exact source profile.",'
        '"protected_impact":{"forbidden_targets":[],"registry_ids":[],"result":"NO_PROTECTED_MUTATION",'
        '"shared_consumers":[]},"reason":"SOURCE_ABSENT_EXACT_PROFILE","record_id":"' + RECORD_ID + '",'
        '"schema":"clothmorph.terminal-exclusion","schema_version":1,'
        '"scope_statement":"Exclude only the exact synthetic SBBF route.",'
        '"source_profile_id":"SYNTHETIC_PROFILE"}'
    )


def test_event_id_is_uppercase_digest_of_the_canonical_payload():
    event = exclusion_fixture()

    assert exclusion_event_id(event) == "EXCLUSION_3B12A2D2EC7C5B62A4AEEBB3DEEEA55B20791A2D6E7327CE153A26BFF81A075F"


def test_event_id_changes_when_a_bound_payload_field_changes():
    event = exclusion_fixture()
    changed = exclusion_fixture(scope_statement="Exclude a different exact route.")

    assert exclusion_event_id(event) != exclusion_event_id(changed)


@pytest.mark.parametrize(
    "reason,claim",
    [
        ("SOURCE_ABSENT_EXACT_PROFILE", "SOURCE_ABSENT_EXACT_PROFILE: route absent."),
        ("NO_RELEASE_PERMISSION", "NO_RELEASE_PERMISSION: license forbids distribution."),
        ("NON_WEARABLE_OR_UNSUPPORTED_BODY_TUPLE", "NON_WEARABLE_OR_UNSUPPORTED_BODY_TUPLE: tuple unsupported."),
        ("PROTECTED_NATIVE_ONLY", "PROTECTED_NATIVE_ONLY: protected source-native route."),
        ("UNRESOLVED_SOURCE_CONTRACT_AFTER_EXHAUSTIVE_AUDIT", "UNRESOLVED_SOURCE_CONTRACT_AFTER_EXHAUSTIVE_AUDIT: retained evidence contradicts."),
        ("INCOMPATIBLE_MUTUALLY_EXCLUSIVE_PROFILE", "INCOMPATIBLE_MUTUALLY_EXCLUSIVE_PROFILE: alternate artifact owns profile."),
    ],
)
def test_each_non_geometry_allowed_reason_requires_and_accepts_its_reason_bound_evidence(reason, claim):
    event = signed_event(reason=reason, evidence=[{
        "path": "evidence/reason.json", "sha256": EVIDENCE_SHA256, "claim": claim,
    }])

    assert validate_exclusion_event(event, ledger_record=ledger_record(), evidence_hashes={EVIDENCE_SHA256}) == []


def test_geometry_exhaustion_requires_gates_three_architectures_and_unfixable_claim():
    event = signed_event(
        reason="NO_SAFE_GEOMETRY_AVAILABLE",
        attempted_architectures=["deform", "transfer", "component-preserving projection"],
        fixed_acceptance_gates={"topology": "FAIL", "component": "FAIL"},
        evidence=[{
            "path": "evidence/geometry.json",
            "sha256": EVIDENCE_SHA256,
            "claim": "NO_SAFE_GEOMETRY_AVAILABLE: UNFIXABLE_WITH_AVAILABLE_SAFE_TOOLING.",
        }],
    )

    assert validate_exclusion_event(event, ledger_record=ledger_record(), evidence_hashes={EVIDENCE_SHA256}) == []


def test_rejects_unknown_reason_and_reason_without_its_required_evidence_claim():
    unknown = signed_event(reason="TIME_RAN_OUT")
    missing_claim = signed_event(reason="NO_RELEASE_PERMISSION")

    assert "INVALID_EXCLUSION_REASON:TIME_RAN_OUT" in validate_exclusion_event(
        unknown, ledger_record=ledger_record(), evidence_hashes={EVIDENCE_SHA256}
    )
    assert "MISSING_REASON_EVIDENCE:NO_RELEASE_PERMISSION" in validate_exclusion_event(
        missing_claim, ledger_record=ledger_record(), evidence_hashes={EVIDENCE_SHA256}
    )


def test_rejects_blank_binding_fields_lowercase_hash_and_tampered_event_id():
    event = signed_event(record_id="", identity_sha256="b" * 64, source_profile_id="", mode="")
    event["event_id"] = "EXCLUSION_" + "F" * 64

    errors = validate_exclusion_event(event, ledger_record=ledger_record(), evidence_hashes={EVIDENCE_SHA256})

    assert "BLANK:record_id" in errors
    assert "INVALID_SHA256:identity_sha256" in errors
    assert "BLANK:source_profile_id" in errors
    assert "BLANK:mode" in errors
    assert "EVENT_ID_MISMATCH" in errors


def test_rejects_mismatched_record_identity_profile_and_unknown_mode():
    event = signed_event(record_id="LEDGER_" + "D" * 64, identity_sha256="E" * 64, source_profile_id="OTHER", mode="invalid")

    errors = validate_exclusion_event(event, ledger_record=ledger_record(), evidence_hashes={EVIDENCE_SHA256})

    assert "RECORD_ID_MISMATCH" in errors
    assert "IDENTITY_SHA256_MISMATCH" in errors
    assert "SOURCE_PROFILE_ID_MISMATCH" in errors
    assert "INVALID_MODE:invalid" in errors


def test_rejects_missing_or_unregistered_evidence_hashes():
    missing = signed_event(evidence=[])
    unregistered = signed_event(evidence=[{
        "path": "evidence/missing.json", "sha256": "D" * 64,
        "claim": "SOURCE_ABSENT_EXACT_PROFILE: route absent.",
    }])

    assert "EVIDENCE_REQUIRED" in validate_exclusion_event(
        missing, ledger_record=ledger_record(), evidence_hashes={EVIDENCE_SHA256}
    )
    assert "UNREGISTERED_EVIDENCE_SHA256:0" in validate_exclusion_event(
        unregistered, ledger_record=ledger_record(), evidence_hashes={EVIDENCE_SHA256}
    )


def test_rejects_any_protected_impact_or_nonzero_mutation_result():
    event = signed_event(protected_impact={
        "registry_ids": ["PROTECTED"], "shared_consumers": [], "forbidden_targets": [],
        "result": "NO_PROTECTED_MUTATION",
    })

    errors = validate_exclusion_event(event, ledger_record=ledger_record(), evidence_hashes={EVIDENCE_SHA256})

    assert "PROTECTED_IMPACT_DECLARED:registry_ids" in errors


def test_tiefling_record_cannot_be_excluded():
    tiefling = ledger_record(source_module={
        "folder": "ClothMorphTieflingBT1_TEST",
        "pak": "ClothMorphTieflingBT1_TEST.pak",
        "uuid": "b57bab2c-5679-5445-8fee-ca8c282990a5",
        "pak_sha256": TIEFLING_PAK_SHA256,
        "profile_digest": "E" * 64,
    })

    errors = validate_exclusion_event(
        signed_event(source_profile_id="ClothMorphTieflingBT1_TEST"),
        ledger_record=tiefling,
        evidence_hashes={EVIDENCE_SHA256},
    )

    assert "EXCLUSION_FORBIDDEN_ACCEPTED_TIEFLING" in errors


def test_selector_uses_newest_non_revoked_event_for_exact_record_and_mode():
    older = signed_event(created_utc="2026-09-01T12:00:00Z")
    newer = signed_event(created_utc="2026-09-01T12:01:00Z")
    unrelated = signed_event(record_id="LEDGER_" + "C" * 64, created_utc="2026-09-01T12:02:00Z")

    selection = select_current_exclusion([older, unrelated, newer], RECORD_ID, "sbbf")

    assert isinstance(selection, ExclusionSelection)
    assert selection.event == newer
    assert selection.errors == ()


def test_selector_refuses_duplicate_event_ids_and_same_time_conflicting_events():
    event = signed_event()
    duplicate = deepcopy(event)
    conflict = signed_event(reason="NO_RELEASE_PERMISSION", evidence=[{
        "path": "evidence/permission.json", "sha256": EVIDENCE_SHA256,
        "claim": "NO_RELEASE_PERMISSION: license forbids distribution.",
    }])

    duplicate_selection = select_current_exclusion([event, duplicate], RECORD_ID, "sbbf")
    conflict_selection = select_current_exclusion([event, conflict], RECORD_ID, "sbbf")

    assert duplicate_selection.event is None
    assert duplicate_selection.errors == ("DUPLICATE_EXCLUSION_EVENT_ID",)
    assert conflict_selection.event is None
    assert conflict_selection.errors == ("CONFLICTING_EXCLUSION_EVENTS",)


def test_selector_honors_a_later_valid_revocation_and_refuses_orphan_revocation():
    event = signed_event()
    revocation = {
        "event_type": "REVOCATION",
        "record_id": RECORD_ID,
        "mode": "sbbf",
        "revokes_event_id": event["event_id"],
        "created_utc": "2026-09-01T12:01:00Z",
    }
    orphan = dict(revocation, revokes_event_id="EXCLUSION_" + "F" * 64)

    revoked = select_current_exclusion([event, revocation], RECORD_ID, "sbbf")
    orphaned = select_current_exclusion([orphan], RECORD_ID, "sbbf")

    assert revoked.event is None
    assert revoked.errors == ()
    assert orphaned.event is None
    assert orphaned.errors == ("REVOCATION_WITHOUT_PRIOR_EVENT",)


def test_selector_refuses_a_same_time_revocation_as_an_ambiguous_history():
    event = signed_event()
    same_time_revocation = {
        "event_type": "REVOCATION",
        "record_id": RECORD_ID,
        "mode": "sbbf",
        "revokes_event_id": event["event_id"],
        "created_utc": "2026-09-01T12:00:00Z",
    }

    selection = select_current_exclusion([event, same_time_revocation], RECORD_ID, "sbbf")

    assert selection.event is None
    assert selection.errors == ("CONFLICTING_EXCLUSION_EVENTS",)

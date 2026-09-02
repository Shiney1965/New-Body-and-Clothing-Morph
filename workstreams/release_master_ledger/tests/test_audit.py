import pytest

from workstreams.release_master_ledger.audit import InventorySets, build_completeness_audit
from workstreams.release_master_ledger.identity import canonical_json, sha256_text
from workstreams.release_master_ledger.models import CanonicalIdentityFields, LedgerRecord, Observation
from workstreams.release_master_ledger.reconcile import ReconciliationResult, reconcile_observations
from workstreams.release_master_ledger.tests.test_exclusions import (
    IDENTITY_SHA256,
    RECORD_ID,
    VERIFIED_EVIDENCE,
    exclusion_event_id,
    ledger_record,
    signed_event,
)
from workstreams.release_master_ledger.tests.test_validation import complete_record_fixture


def observation(observation_id, *, root_template_uuid="22222222-2222-2222-2222-222222222222", disposition="DEFERRED_WITH_CAUSE", release_blocking=True):
    return Observation(
        observation_id=observation_id,
        observation_kind="SYNTHETIC",
        identity_fields=CanonicalIdentityFields(
            source_module_uuid="11111111-1111-1111-1111-111111111111",
            source_profile_digest="A" * 64,
            creation_path_kind="root_template",
            root_template_uuid=root_template_uuid,
            stats_entry="ARM_Test",
            inheritance_digest="B" * 64,
            effective_slot="Underwear",
            body_tuple=("Human", "Female", "BT1", "Regular", "HUM_F"),
            ordered_source_vrs=("vr-a",),
            component_contract_digest="C" * 64,
        ),
        source_reference=f"{observation_id}.json",
        evidence_files=(f"{observation_id}.json",),
        payload={"disposition": disposition, "release_blocking": release_blocking},
    )


def inventories(**overrides):
    values = {
        "source_observations": frozenset(),
        "prior_evidence": frozenset(),
        "packaged_records": frozenset(),
        "required_source_profiles": frozenset(),
        "complete_source_profiles": frozenset(),
        "section_19_gates": {},
    }
    values.update(overrides)
    return InventorySets(**values)


EVENT_FILE_PATH = "history/synthetic.json"
EVENT_FILE_SHA256 = "A" * 64
EVENT_FILE_REGISTRY = {EVENT_FILE_PATH: EVENT_FILE_SHA256}


def terminal_exclusion_record(event, **overrides):
    """Build one complete record whose terminal state claims this exact event."""
    data = complete_record_fixture()
    data.update({
        "record_id": RECORD_ID,
        "identity_sha256": IDENTITY_SHA256,
        "source_module": ledger_record()["source_module"],
        "permission": ledger_record()["permission"],
        "classification": ledger_record()["classification"],
        "body_tuple": ledger_record()["body_tuple"],
        "source_route": ledger_record()["source_route"],
        "protected_relations": ledger_record()["protected_relations"],
        "disposition": "OUT_OF_SCOPE_WITH_PROOF",
        "blocker_codes": [],
        "release_blocking": False,
        "shipped_package_id": "UNKNOWN_SHIPPED_PACKAGE",
            "terminal_exclusion": {
                "event": event,
                "event_file": {
                    "relative_path": EVENT_FILE_PATH,
                    "sha256": EVENT_FILE_SHA256,
                    "canonical_event_sha256": sha256_text(canonical_json(event)),
                },
            },
    })
    data.update(overrides)
    return LedgerRecord(**data)


def audit_terminal_event(record, events, *, evidence=VERIFIED_EVIDENCE, event_files=EVENT_FILE_REGISTRY):
    result = ReconciliationResult(
        records=(record,), observation_to_record={}, conflicts=(),
    )
    return build_completeness_audit(
        result,
        inventories(),
        exclusion_events=events,
        verified_evidence=evidence,
        discovered_event_files=event_files,
    )


def test_missing_source_observation_is_reported_sorted():
    result = reconcile_observations([observation("obs-1")])

    audit = build_completeness_audit(
        result, inventories(source_observations=frozenset({"obs-2", "obs-1"}))
    )

    assert audit["missing_from_ledger"] == ["obs-2"]


def test_exact_audit_sets_are_sorted_and_fail_closed():
    result = reconcile_observations([
        observation("obs-1"), observation("obs-orphan", root_template_uuid="root-orphan"),
    ])

    audit = build_completeness_audit(
        result,
        inventories(
            source_observations=frozenset({"obs-1", "obs-2"}),
            prior_evidence=frozenset({"evidence-a", "evidence-z"}),
            packaged_records=frozenset({"package-a", "package-z"}),
            required_source_profiles=frozenset({"profile-a", "profile-z"}),
            complete_source_profiles=frozenset({"profile-a"}),
        ),
    )

    assert audit["missing_from_ledger"] == ["obs-2"]
    assert audit["duplicate_identity"] == []
    assert audit["unreferenced_prior_evidence"] == ["evidence-a", "evidence-z"]
    assert audit["packaged_without_ledger"] == ["package-a", "package-z"]
    assert audit["ledger_without_source"] == [result.observation_to_record["obs-orphan"]]
    assert audit["in_scope_nonterminal"] == [record.record_id for record in result.records]
    assert audit["source_complete"] is False
    assert audit["release_complete"] is False
    assert audit["required_source_profiles_complete"] is False


def test_corroborating_exact_join_is_not_a_duplicate_identity():
    result = reconcile_observations([observation("obs-z"), observation("obs-a")])

    audit = build_completeness_audit(
        result,
        inventories(source_observations=frozenset({"obs-z", "obs-a"})),
    )

    assert len(result.records) == 1
    assert audit["duplicate_identity"] == []


def test_corroborating_non_source_join_does_not_make_sourced_record_ledger_without_source():
    result = reconcile_observations([observation("source"), observation("corroborating")])

    audit = build_completeness_audit(
        result, inventories(source_observations=frozenset({"source"}))
    )

    assert len(result.records) == 1
    assert audit["ledger_without_source"] == []


def test_standalone_corroborating_record_is_ledger_without_source():
    result = reconcile_observations([observation("corroborating")])

    audit = build_completeness_audit(result, inventories())

    assert audit["ledger_without_source"] == [result.records[0].record_id]


def test_in_scope_nonterminal_is_not_hidden_by_zero_unclassified():
    result = reconcile_observations([observation("obs-1", disposition="DEFERRED_WITH_CAUSE")])

    audit = build_completeness_audit(
        result, inventories(source_observations=frozenset({"obs-1"}))
    )

    assert audit["unclassified_count"] == 0
    assert audit["in_scope_nonterminal"] == [result.records[0].record_id]
    assert audit["source_complete"] is True
    assert audit["release_complete"] is False


def test_later_gates_cannot_be_assumed_true_without_explicit_true_values():
    result = reconcile_observations([observation("terminal", disposition="SHIPPED_REFIT", release_blocking=False)])

    audit = build_completeness_audit(
        result,
        inventories(source_observations=frozenset({"terminal"}), section_19_gates={}),
    )

    assert audit["source_complete"] is True
    assert audit["release_complete"] is False


def test_profile_ids_are_emitted_for_traceability():
    audit = build_completeness_audit(
        reconcile_observations([]),
        inventories(
            required_source_profiles=frozenset({"profile-a", "profile-b"}),
            complete_source_profiles=frozenset({"profile-a"}),
        ),
    )

    assert audit["required_source_profiles"] == ["profile-a", "profile-b"]
    assert audit["complete_source_profiles"] == ["profile-a"]
    assert audit["missing_source_profiles"] == ["profile-b"]


def test_current_valid_terminal_exclusion_is_audited_and_no_longer_nonterminal():
    event = signed_event()

    audit = audit_terminal_event(terminal_exclusion_record(event), (event,))

    assert audit["excluded_with_proof"] == [RECORD_ID]
    assert audit["exclusion_validation_failures"] == []
    assert audit["excluded_but_packaged"] == []
    assert audit["in_scope_nonterminal"] == []


@pytest.mark.parametrize(
    "mutate_attachment",
    [
        pytest.param(
            lambda summary: summary.pop("event_file"),
            id="missing-event-file",
        ),
        pytest.param(
            lambda summary: summary["event_file"].update({"relative_path": "history/wrong.json"}),
            id="wrong-event-file-path",
        ),
        pytest.param(
            lambda summary: summary["event_file"].update({"sha256": "B" * 64}),
            id="wrong-event-file-sha256",
        ),
        pytest.param(
            lambda summary: summary["event_file"].update({"canonical_event_sha256": "B" * 64}),
            id="wrong-canonical-event-sha256",
        ),
        pytest.param(
            lambda summary: summary.update({"event_file": []}),
            id="malformed-event-file",
        ),
    ],
)
def test_invalid_event_file_provenance_remains_nonterminal(mutate_attachment):
    """Breaks if audit accepts a current event without its immutable attachment."""
    event = signed_event()
    record = terminal_exclusion_record(event)
    mutate_attachment(record.terminal_exclusion)

    audit = audit_terminal_event(record, (event,))

    assert audit["excluded_with_proof"] == []
    assert audit["exclusion_validation_failures"] == [RECORD_ID]
    assert audit["excluded_but_packaged"] == []
    assert audit["in_scope_nonterminal"] == [RECORD_ID]


@pytest.mark.parametrize(
    ("mutate", "event_history", "record_overrides"),
    [
        pytest.param(
            lambda event: event["evidence"].clear(),
            lambda event: (event,),
            {},
            id="missing-evidence",
        ),
        pytest.param(
            lambda event: None,
            lambda event: (),
            {"terminal_exclusion": None},
            id="missing-event",
        ),
        pytest.param(
            lambda event: event["protected_impact"].update({"registry_ids": ["PROTECTED"]}),
            lambda event: (event,),
            {},
            id="protected-impact",
        ),
        pytest.param(
            lambda event: event.update({"identity_sha256": "C" * 64}),
            lambda event: (event,),
            {},
            id="identity-mismatch",
        ),
        pytest.param(
            lambda event: event.update({"reason": "TIME_RAN_OUT", "reason_proof": {}}),
            lambda event: (event,),
            {},
            id="forbidden-reason",
        ),
        pytest.param(
            lambda event: None,
            lambda event: (
                event,
                signed_event(created_utc="2026-09-01T12:01:00Z"),
            ),
            {},
            id="stale-event",
        ),
        pytest.param(
            lambda event: None,
            lambda event: (event,),
            {"release_blocking": True},
            id="release-blocking-still-true",
        ),
    ],
)
def test_invalid_or_stale_terminal_exclusion_remains_nonterminal(
    mutate, event_history, record_overrides,
):
    event = signed_event()
    mutate(event)
    event["event_id"] = exclusion_event_id(event)

    audit = audit_terminal_event(
        terminal_exclusion_record(event, **record_overrides), event_history(event),
    )

    assert audit["excluded_with_proof"] == []
    assert audit["exclusion_validation_failures"] == [RECORD_ID]
    assert audit["excluded_but_packaged"] == []
    assert audit["in_scope_nonterminal"] == [RECORD_ID]


def test_packaged_terminal_exclusion_is_explicitly_blocking():
    event = signed_event()
    record = terminal_exclusion_record(
        event, shipped_package_id="PACKAGE_SHA256:" + "C" * 64,
    )

    audit = audit_terminal_event(record, (event,))

    assert audit["excluded_with_proof"] == []
    assert audit["exclusion_validation_failures"] == []
    assert audit["excluded_but_packaged"] == [RECORD_ID]
    assert audit["in_scope_nonterminal"] == [RECORD_ID]

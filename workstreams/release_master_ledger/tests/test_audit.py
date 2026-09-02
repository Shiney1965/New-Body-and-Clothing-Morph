import pytest
from copy import deepcopy
from dataclasses import replace

from workstreams.release_master_ledger.audit import InventorySets, build_completeness_audit
from workstreams.release_master_ledger.exclusions import ZERO_CLAIM_MODE_ROUTE
from workstreams.release_master_ledger.identity import canonical_json, sha256_text
from workstreams.release_master_ledger.models import CanonicalIdentityFields, LedgerRecord, Observation
from workstreams.release_master_ledger.reconcile import ReconciliationResult, reconcile_observations
from workstreams.release_master_ledger.tests.test_exclusions import (
    IDENTITY_SHA256,
    RECORD_ID,
    VERIFIED_EVIDENCE,
    exclusion_event_id,
    ledger_record,
    RELEASE_MODES,
    signed_event,
)
from workstreams.release_master_ledger.tests.test_validation import (
    complete_record_fixture,
    mode_scope_fixture,
    terminal_exclusion_fixture,
)


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
COMPLETE_AUTHORITY_CONTEXT = {
    "provider_authority_present": True,
    "provider_authority_complete": True,
    "package_authority_present": True,
    "package_authority_complete": True,
}


def _mode_summary(event, mode):
    path = f"history/{mode}.json"
    digest = chr(ord("A") + RELEASE_MODES.index(mode)) * 64
    return {
        "event": event,
        "event_file": {
            "relative_path": path,
            "sha256": digest,
            "canonical_event_sha256": sha256_text(canonical_json(event)),
        },
    }


def terminal_exclusion_record(events, **overrides):
    """Build one complete record with exact per-mode terminal attachments."""
    if isinstance(events, dict):
        events = (events,)
    events = tuple(events)
    data = complete_record_fixture()
    mode_scope = mode_scope_fixture()
    terminal_exclusion = terminal_exclusion_fixture()
    for event in events:
        mode = event["mode"]
        mode_scope[mode] = {
            "advertised": False,
            "terminal_state": "OUT_OF_SCOPE_WITH_PROOF",
        }
        terminal_exclusion[mode] = _mode_summary(event, mode)
    record_closed = set(event["mode"] for event in events) == set(RELEASE_MODES)
    data.update({
        "record_id": RECORD_ID,
        "identity_sha256": IDENTITY_SHA256,
        "source_module": ledger_record()["source_module"],
        "permission": ledger_record()["permission"],
        "classification": ledger_record()["classification"],
        "body_tuple": ledger_record()["body_tuple"],
        "source_route": ledger_record()["source_route"],
        "mode_routes": {mode: dict(ZERO_CLAIM_MODE_ROUTE) for mode in RELEASE_MODES},
        "mode_scope": mode_scope,
        "protected_relations": ledger_record()["protected_relations"],
        "disposition": (
            "OUT_OF_SCOPE_WITH_PROOF" if record_closed else "DEFERRED_WITH_CAUSE"
        ),
        "blocker_codes": [] if record_closed else ["SYNTHETIC_BLOCKER"],
        "release_blocking": not record_closed,
        "shipped_package_id": "UNKNOWN_SHIPPED_PACKAGE",
        "terminal_exclusion": terminal_exclusion,
    })
    data.update(overrides)
    return LedgerRecord(**data)


def _event_file_registry(events):
    return {
        f"history/{event['mode']}.json": (
            chr(ord("A") + RELEASE_MODES.index(event["mode"])) * 64
        )
        for event in events
        if event.get("event_type", "EXCLUSION") == "EXCLUSION"
        and event.get("mode") in RELEASE_MODES
    }


def audit_terminal_event(
    record, events, *, evidence=VERIFIED_EVIDENCE, event_files=None,
    provider_claims=None, package_claims=None,
):
    provider_claims = {} if provider_claims is None else provider_claims
    package_claims = {} if package_claims is None else package_claims
    result = ReconciliationResult(
        records=(record,), observation_to_record={}, conflicts=(),
    )
    return build_completeness_audit(
        result,
        inventories(),
        exclusion_events=events,
        verified_evidence=evidence,
        discovered_event_files=(
            _event_file_registry(events) if event_files is None else event_files
        ),
        independent_provider_claims=provider_claims,
        independent_package_claims=package_claims,
        **COMPLETE_AUTHORITY_CONTEXT,
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


def test_one_valid_mode_exclusion_is_audited_but_cannot_close_the_record():
    event = signed_event()

    audit = audit_terminal_event(terminal_exclusion_record(event), (event,))

    assert audit["excluded_modes_with_proof"] == [f"{RECORD_ID}:sbbf"]
    assert audit["excluded_with_proof"] == []
    assert audit["exclusion_validation_failures"] == []
    assert audit["exclusion_history_failures"] == []
    assert audit["excluded_but_packaged"] == []
    assert audit["in_scope_nonterminal"] == [RECORD_ID]


def test_all_four_valid_mode_exclusions_are_required_to_close_the_record():
    events = tuple(
        signed_event(mode=mode, created_utc=f"2026-09-01T12:0{index}:00Z")
        for index, mode in enumerate(RELEASE_MODES)
    )

    audit = audit_terminal_event(terminal_exclusion_record(events), events)

    assert audit["excluded_modes_with_proof"] == [
        f"{RECORD_ID}:{mode}" for mode in sorted(RELEASE_MODES)
    ]
    assert audit["excluded_with_proof"] == [RECORD_ID]
    assert audit["exclusion_validation_failures"] == []
    assert audit["exclusion_history_failures"] == []
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
            lambda summary: summary["event_file"].update({"sha256": "E" * 64}),
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
    mutate_attachment(record.terminal_exclusion["sbbf"])

    audit = audit_terminal_event(record, (event,))

    assert audit["excluded_with_proof"] == []
    assert audit["excluded_modes_with_proof"] == []
    assert audit["exclusion_validation_failures"] == [RECORD_ID]
    assert audit["excluded_but_packaged"] == []
    assert audit["in_scope_nonterminal"] == [RECORD_ID]


@pytest.mark.parametrize(
    ("mutate", "event_history"),
    [
        pytest.param(
            lambda event: event["evidence"].clear(),
            lambda event: (event,),
            id="missing-evidence",
        ),
        pytest.param(
            lambda event: event["protected_impact"].update({"registry_ids": ["PROTECTED"]}),
            lambda event: (event,),
            id="protected-impact",
        ),
        pytest.param(
            lambda event: event.update({"identity_sha256": "C" * 64}),
            lambda event: (event,),
            id="identity-mismatch",
        ),
        pytest.param(
            lambda event: event.update({"reason": "TIME_RAN_OUT", "reason_proof": {}}),
            lambda event: (event,),
            id="forbidden-reason",
        ),
        pytest.param(
            lambda event: event.update({"unexpected": "forbidden"}),
            lambda event: (event,),
            id="closed-schema",
        ),
        pytest.param(
            lambda event: None,
            lambda event: (
                event,
                signed_event(created_utc="2026-09-01T12:01:00Z"),
            ),
            id="stale-event",
        ),
    ],
)
def test_invalid_or_stale_terminal_exclusion_remains_nonterminal(
    mutate, event_history,
):
    event = signed_event()
    mutate(event)
    event["event_id"] = exclusion_event_id(event)

    audit = audit_terminal_event(
        terminal_exclusion_record(event), event_history(event),
    )

    assert audit["excluded_with_proof"] == []
    assert audit["excluded_modes_with_proof"] == []
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
    assert audit["excluded_modes_with_proof"] == []
    assert audit["exclusion_validation_failures"] == [RECORD_ID]
    assert audit["excluded_but_packaged"] == [RECORD_ID]
    assert audit["in_scope_nonterminal"] == [RECORD_ID]


@pytest.mark.parametrize(
    ("kind", "expected"),
    [
        ("provider", f"INDEPENDENT_PROVIDER_CLAIM:{RECORD_ID}:sbbf"),
        ("package", f"INDEPENDENT_PACKAGE_CLAIM:{RECORD_ID}:sbbf"),
    ],
)
def test_audit_rechecks_independent_provider_and_package_claims(kind, expected):
    event = signed_event()
    claims = {(RECORD_ID, "sbbf"): ("CLAIM",)}

    audit = audit_terminal_event(
        terminal_exclusion_record(event), (event,),
        provider_claims=claims if kind == "provider" else {},
        package_claims=claims if kind == "package" else {},
    )

    assert expected in audit["exclusion_history_failures"]
    assert audit["excluded_modes_with_proof"] == []
    assert audit["exclusion_validation_failures"] == [RECORD_ID]


@pytest.mark.parametrize(
    ("channel", "kind"),
    [
        pytest.param("target_vrs", "provider", id="independent-target-vrs"),
        pytest.param("target_paths", "provider", id="independent-target-paths"),
        pytest.param("payload_hashes", "provider", id="independent-payload-hashes"),
        pytest.param("provider_id", "provider", id="independent-provider-id"),
        pytest.param("provenance", "provider", id="independent-provenance"),
        pytest.param("package_ownership", "package", id="independent-package-ownership"),
        pytest.param("shipped_package", "package", id="independent-shipped-package"),
    ],
)
def test_lifecycle_claim_each_independent_preclaim_channel_remains_nonterminal(
    channel, kind,
):
    """Breaks if any independent claim channel can be erased by attachment."""
    events = tuple(
        signed_event(mode=mode, created_utc=f"2026-09-01T12:0{index}:00Z")
        for index, mode in enumerate(RELEASE_MODES)
    )
    claims = {(RECORD_ID, "sbbf"): (channel,)}

    audit = audit_terminal_event(
        terminal_exclusion_record(events),
        events,
        provider_claims=claims if kind == "provider" else {},
        package_claims=claims if kind == "package" else {},
    )

    assert audit["exclusion_validation_failures"] == [RECORD_ID]
    assert audit["in_scope_nonterminal"] == [RECORD_ID]
    assert audit["excluded_with_proof"] == []


@pytest.mark.parametrize(
    "mutate",
    [
        pytest.param(
            lambda record: record.mode_scope["sbbf"].update({"advertised": True}),
            id="record-advertised",
        ),
        pytest.param(
            lambda record: record.mode_scope["sbbf"].update({"terminal_state": "NONTERMINAL"}),
            id="record-terminal-state",
        ),
        pytest.param(
            lambda record: record.mode_routes["sbbf"].update({"behavior": "UNASSESSED_ROUTE_BEHAVIOR"}),
            id="record-behavior",
        ),
        pytest.param(
            lambda record: record.mode_routes["sbbf"].update({"target_vrs": ["VR_CLAIM"]}),
            id="record-target-vrs",
        ),
        pytest.param(
            lambda record: record.mode_routes["sbbf"].update({"target_paths": ["Public/Claim.GR2"]}),
            id="record-target-paths",
        ),
        pytest.param(
            lambda record: record.mode_routes["sbbf"].update({"payload_hashes": ["7" * 64]}),
            id="record-payload-hashes",
        ),
        pytest.param(
            lambda record: record.mode_routes["sbbf"].update({"provider_id": "CLAIMED_PROVIDER"}),
            id="record-provider-id",
        ),
        pytest.param(
            lambda record: record.mode_routes["sbbf"].update({"provenance": "CLAIMED_PROVENANCE"}),
            id="record-provenance",
        ),
        pytest.param(
            lambda record: record.mode_routes["sbbf"].update({"static_status": "STATIC_UNASSESSED"}),
            id="record-static-status",
        ),
        pytest.param(
            lambda record: record.mode_routes["sbbf"].update({"gameplay_status": "GAMEPLAY_UNASSESSED"}),
            id="record-gameplay-status",
        ),
        pytest.param(
            lambda record: record.mode_routes["sbbf"].update({"save_reload_status": "SAVE_RELOAD_UNASSESSED"}),
            id="record-save-reload-status",
        ),
        pytest.param(
            lambda record: replace(
                record, shipped_package_id="PACKAGE_SHA256:" + "7" * 64
            ),
            id="record-shipped-package",
        ),
    ],
)
def test_lifecycle_claim_each_attached_record_claim_channel_remains_nonterminal(
    mutate,
):
    """Breaks if attached audit accepts any non-excluded record representation."""
    events = tuple(
        signed_event(mode=mode, created_utc=f"2026-09-01T12:0{index}:00Z")
        for index, mode in enumerate(RELEASE_MODES)
    )
    record = terminal_exclusion_record(events)
    mutated = mutate(record)
    if mutated is not None:
        record = mutated

    audit = audit_terminal_event(record, events)

    assert audit["exclusion_validation_failures"] == [RECORD_ID]
    assert audit["in_scope_nonterminal"] == [RECORD_ID]
    assert audit["excluded_with_proof"] == []


def test_audit_refuses_exclusion_without_independent_claim_context():
    event = signed_event()
    record = terminal_exclusion_record(event)
    result = ReconciliationResult(
        records=(record,), observation_to_record={}, conflicts=(),
    )

    audit = build_completeness_audit(
        result, inventories(), exclusion_events=(event,),
        verified_evidence=VERIFIED_EVIDENCE,
        discovered_event_files=_event_file_registry((event,)),
    )

    assert audit["excluded_modes_with_proof"] == []
    assert audit["exclusion_validation_failures"] == [RECORD_ID]
    assert (
        f"MISSING_INDEPENDENT_EXCLUSION_CLAIM_CONTEXT:{RECORD_ID}:sbbf"
        in audit["exclusion_history_failures"]
    )


def test_unmatched_history_is_reported_globally_with_a_stable_code():
    unmatched_id = "LEDGER_" + "E" * 64
    unmatched = signed_event(record_id=unmatched_id)
    record = terminal_exclusion_record(())

    audit = audit_terminal_event(record, (unmatched,))

    assert audit["exclusion_history_failures"] == [
        f"UNMATCHED_EXCLUSION_RECORD:{unmatched_id}"
    ]
    assert audit["exclusion_validation_failures"] == []


def test_global_exclusion_history_failure_prevents_release_completion():
    unmatched_id = "LEDGER_" + "E" * 64
    unmatched = signed_event(record_id=unmatched_id)
    section_19 = {
        name: True for name in (
            "protected_controls", "in_scope_terminal", "in_scope_terminal_modes",
            "package_only_gameplay", "source_observations_exactly_once",
            "route_ownership", "permissions_release_cleared",
            "package_profile_build_fresh_extract",
            "gameplay_class_random_save_reload", "advertised_combined_profiles",
            "installer_restore",
        )
    }

    audit = build_completeness_audit(
        ReconciliationResult(records=(), observation_to_record={}, conflicts=()),
        inventories(section_19_gates=section_19),
        exclusion_events=(unmatched,),
    )

    assert audit["source_complete"] is True
    assert audit["in_scope_nonterminal"] == []
    assert audit["exclusion_history_failures"] == [
        f"UNMATCHED_EXCLUSION_RECORD:{unmatched_id}"
    ]
    assert audit["release_complete"] is False


def test_orphan_revocation_is_reported_globally_with_a_stable_code():
    orphan = {
        "event_type": "REVOCATION",
        "record_id": RECORD_ID,
        "mode": "sbbf",
        "revokes_event_id": "EXCLUSION_" + "F" * 64,
        "created_utc": "2026-09-01T12:01:00Z",
    }
    record = terminal_exclusion_record(())

    audit = audit_terminal_event(record, (orphan,))

    assert audit["exclusion_history_failures"] == [
        f"REVOCATION_WITHOUT_PRIOR_EVENT:{RECORD_ID}:sbbf"
    ]
    assert audit["exclusion_validation_failures"] == [RECORD_ID]

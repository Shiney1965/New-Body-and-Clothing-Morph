from workstreams.release_master_ledger.audit import InventorySets, build_completeness_audit
from workstreams.release_master_ledger.models import CanonicalIdentityFields, Observation
from workstreams.release_master_ledger.reconcile import reconcile_observations


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


def test_duplicate_identity_is_a_sorted_observation_set():
    result = reconcile_observations([observation("obs-z"), observation("obs-a")])

    audit = build_completeness_audit(
        result,
        inventories(source_observations=frozenset({"obs-z", "obs-a"})),
    )

    assert audit["duplicate_identity"] == ["obs-a", "obs-z"]


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

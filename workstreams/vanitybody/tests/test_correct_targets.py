from workstreams.vanitybody.anchors import load_anchor_contracts
from workstreams.vanitybody.correct_targets import correction_targets


def test_each_and_only_approved_anchor_receives_a_fresh_target_visual_resource():
    targets = correction_targets(load_anchor_contracts())
    assert {(target.root_uuid, target.mode) for target in targets} == {
        (anchor.root_uuid, anchor.mode) for anchor in load_anchor_contracts()
    }
    assert len({target.target_visual_resource_uuid for target in targets}) == 5


def test_protected_modes_have_no_target_visual_resource():
    targets = correction_targets(load_anchor_contracts())
    addressed = {(target.root_uuid, target.mode) for target in targets}
    for anchor in load_anchor_contracts():
        assert all((anchor.root_uuid, mode) not in addressed for mode in anchor.protected_modes)

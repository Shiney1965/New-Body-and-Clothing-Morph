from workstreams.vanitybody.anchors import (
    SATIN_ROOT,
    SERIOUS_BUSINESS_ROOT,
    SEXY_CATSUIT_ROOT,
    WEDDING_ROOT,
    load_anchor_contracts,
)


def test_confirmed_anchor_set_is_exact():
    actual = {(anchor.root_uuid, anchor.mode) for anchor in load_anchor_contracts()}
    assert actual == {
        (WEDDING_ROOT, "vanilla"),
        (WEDDING_ROOT, "sbbf"),
        (SATIN_ROOT, "vanilla"),
        (SERIOUS_BUSINESS_ROOT, "vanilla"),
        (SEXY_CATSUIT_ROOT, "vanilla"),
    }


def test_protected_modes_are_not_correction_targets():
    targets = {(anchor.root_uuid, anchor.mode) for anchor in load_anchor_contracts()}
    assert (WEDDING_ROOT, "bcb") not in targets
    assert (SATIN_ROOT, "sbbf") not in targets
    assert (SATIN_ROOT, "bcb") not in targets
    assert (SERIOUS_BUSINESS_ROOT, "sbbf") not in targets
    assert (SERIOUS_BUSINESS_ROOT, "bcb") not in targets
    assert (SEXY_CATSUIT_ROOT, "sbbf") not in targets
    assert (SEXY_CATSUIT_ROOT, "bcb") not in targets

import pytest

from true_underwear.local_boundary import CANONICAL_SOURCE_CONFIG
from true_underwear.source_config import _relative_path, load_source_roots


def test_load_source_roots_rejects_noncanonical_config_before_read(tmp_path):
    outside_config = tmp_path / "source_config.json"

    with pytest.raises(ValueError, match="source config"):
        load_source_roots(outside_config)

    assert not outside_config.exists()


def test_relative_source_inputs_may_traverse_from_the_canonical_config_directory():
    relative_input = _relative_path(CANONICAL_SOURCE_CONFIG.parent, "../retained-inputs/Armor.txt")

    assert relative_input == CANONICAL_SOURCE_CONFIG.parent / "../retained-inputs/Armor.txt"

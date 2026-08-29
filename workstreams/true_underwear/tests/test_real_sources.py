import os
from pathlib import Path
import pytest

from true_underwear.inventory import classify_creation_paths
from true_underwear.source_config import load_source_roots


SOURCE_CONFIG = os.environ.get("TRUE_UNDERWEAR_SOURCE_CONFIG")
EVIDENCE_DIR = os.environ.get("TRUE_UNDERWEAR_EVIDENCE_DIR")
pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not SOURCE_CONFIG or not EVIDENCE_DIR,
        reason="requires local source config and ignored generated evidence",
    ),
]


def local_roots():
    assert SOURCE_CONFIG is not None
    return load_source_roots(SOURCE_CONFIG)


def local_evidence_dir() -> Path:
    assert EVIDENCE_DIR is not None
    return Path(EVIDENCE_DIR)


def test_local_config_exposes_declared_sources():
    roots = local_roots()

    assert roots.sources
    assert all(source.stats and source.roots for source in roots.sources)


def test_unresolved_root_only_stats_are_returned_without_persistence(tmp_path):
    roots = local_roots()
    object.__setattr__(roots, "rejections_path", tmp_path / "rejections.json")
    result = classify_creation_paths(roots)

    assert result.rejections
    assert not roots.rejections_path.exists()


def test_local_evidence_directory_is_explicitly_supplied():
    assert local_evidence_dir().is_dir()

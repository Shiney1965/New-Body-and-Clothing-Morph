import json
from pathlib import Path
import pytest

from workstreams.coverage_ledger import build_ledger
from workstreams.coverage_ledger.configuration import LocalConfigurationUnavailable


pytestmark = pytest.mark.integration


def _local_configuration():
    try:
        return build_ledger.load_local_configuration()
    except LocalConfigurationUnavailable as error:
        pytest.skip(str(error))


def test_every_declared_module_has_metadata_and_scan_input_manifest():
    registry = json.loads(_local_configuration().source_registry_path.read_text(encoding="utf-8"))
    for module in registry["source_modules"]:
        assert module["meta_path"]
        assert module["version64"]
        assert module["source_manifest_inputs"]
        assert module["package_identity"]["status"]
        assert all(Path(path).exists() for path in module["source_manifest_inputs"])


def test_source_authority_report_preserves_package_identity_statuses():
    configuration = _local_configuration()
    build_ledger.main(configuration)
    report = json.loads((configuration.evidence_dir / "SOURCE_AUTHORITY_REPORT.json").read_text(encoding="utf-8"))
    assert all(item["package_identity"]["status"] for item in report)

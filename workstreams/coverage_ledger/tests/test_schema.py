import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_disposition_enum_is_binding():
    schema = json.loads((ROOT / "schema.json").read_text(encoding="utf-8"))
    assert set(schema["$defs"]["disposition"]["enum"]) == {
        "ACCEPTED / PROTECT",
        "READY FOR TEST",
        "CONFIRMED DEFECT / CORRECT",
        "MISSING ROUTE / BUILD",
        "DEFERRED WITH CAUSE",
        "OUT OF SCOPE",
    }

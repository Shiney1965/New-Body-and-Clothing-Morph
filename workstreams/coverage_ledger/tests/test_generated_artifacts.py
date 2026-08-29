from collections import Counter
import json
import pytest

from workstreams.coverage_ledger import build_ledger, generate_test_cards
from workstreams.coverage_ledger.configuration import LocalConfigurationUnavailable


pytestmark = pytest.mark.integration


def test_generated_master_and_cards_preserve_every_discovered_identity_once():
    try:
        configuration = build_ledger.load_local_configuration()
    except LocalConfigurationUnavailable as error:
        pytest.skip(str(error))
    build_ledger.main(configuration)
    generate_test_cards.main(configuration)
    evidence = configuration.evidence_dir
    raw = json.loads((evidence / "RAW_WEARABLE_INVENTORY.json").read_text(encoding="utf-8"))
    master = json.loads((evidence / "SCO_SINDAE_MASTER_GARMENT_LEDGER.json").read_text(encoding="utf-8"))
    cards = json.loads((evidence / "CLASS_TEST_CARDS.json").read_text(encoding="utf-8"))

    assert Counter(item["identity"] for item in raw) == Counter(item["identity"] for item in master)
    assert all(item["disposition"] != "UNCLASSIFIED" for item in master)
    ready = sorted(item["identity"] for item in master if item["disposition"] == "READY FOR TEST")
    carded = sorted(identity for card in cards for identity in card["record_identities"])
    assert carded == ready
    assert all(len(card["record_identities"]) <= 12 for card in cards)

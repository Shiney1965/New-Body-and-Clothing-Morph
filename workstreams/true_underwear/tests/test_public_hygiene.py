from pathlib import Path
import re
import xml.etree.ElementTree as ET


FIXTURES = Path(__file__).parent / "fixtures"


def test_inventory_fixtures_use_only_synthetic_identifiers():
    document = ET.parse(FIXTURES / "root_templates.lsx")
    for game_object in document.findall(".//node[@id='GameObjects']"):
        attributes = {
            attribute.get("id", ""): attribute.get("value", "")
            for attribute in game_object.findall("./attribute")
        }
        assert attributes["Name"].startswith("Fixture")
        assert attributes["Stats"].startswith("Fixture")
        assert re.fullmatch(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}", attributes["MapKey"])

    fixture_text = "\n".join(
        path.read_text(encoding="utf-8") for path in FIXTURES.glob("*.txt")
    )
    for identifier in re.findall(r'^(?:new entry|using) "([^"]+)"$', fixture_text, re.MULTILINE):
        assert identifier.startswith("Fixture")

"""Generate bounded, dependency-isolated gameplay cards from the master ledger."""

from __future__ import annotations

from collections import defaultdict
import json
from pathlib import Path
from typing import Iterable

from .models import GarmentRecord, RouteRecord
from .configuration import LocalConfiguration, load_local_configuration, validate_generated_outputs


def _contract_key(record: GarmentRecord) -> tuple[str, str, str, str, str, str, str, str]:
    return (
        record.source_module["uuid"],
        record.effective_slot,
        record.body_family,
        record.topology_family,
        record.component_contract,
        json.dumps(record.package_ownership, sort_keys=True),
        json.dumps(record.candidate_profile, sort_keys=True),
        record.known_defect or "NONE",
    )


def bounded_cards(records: Iterable[GarmentRecord], maximum_records: int = 12) -> list[dict[str, object]]:
    """Return deterministic cards; each READY record occurs once and only once."""
    if maximum_records < 1:
        raise ValueError("maximum_records must be positive")
    groups: dict[tuple[str, str, str, str, str, str, str, str], list[GarmentRecord]] = defaultdict(list)
    for record in records:
        if record.disposition != "READY FOR TEST":
            continue
        groups[_contract_key(record)].append(record)
    cards: list[dict[str, object]] = []
    sequence = 1
    for group, members in sorted(groups.items()):
        ordered = sorted(members, key=lambda item: item.identity)
        for offset in range(0, len(ordered), maximum_records):
            chunk = ordered[offset:offset + maximum_records]
            cards.append({
                "card_id": f"Q{sequence:03d}",
                "source_module_uuid": group[0],
                "effective_slot": group[1],
                "body_family": group[2],
                "topology_family": group[3],
                "component_contract": group[4],
                "package_ownership": json.loads(group[5]),
                "candidate_profile": json.loads(group[6]),
                "defect_mechanism": group[7],
                "record_identities": [record.identity for record in chunk],
                "result": "NOT RUN",
            })
            sequence += 1
    ready_ids = [record.identity for record in records if record.disposition == "READY FOR TEST"]
    card_ids = [identity for card in cards for identity in card["record_identities"]]
    if sorted(ready_ids) != sorted(card_ids) or len(card_ids) != len(set(card_ids)):
        raise ValueError("READY FOR TEST records are not represented exactly once in bounded cards")
    return cards


def _records_from_json(data: list[dict]) -> list[GarmentRecord]:
    return [GarmentRecord(
        identity=item["identity"], source_module=item["source_module"], root_template_uuid=item["root_template_uuid"],
        stats_entry=item["stats_entry"], effective_slot=item["effective_slot"], inheritance_chain=item["inheritance_chain"],
        source_visual_resource_uuid=item["source_visual_resource_uuid"], source_visual_resource_path=item["source_visual_resource_path"],
        body_family=item["body_family"], garment_family=item["garment_family"], topology_family=item["topology_family"],
        component_contract=item.get("component_contract", "UNASSESSED"),
        routes={mode: RouteRecord(**route) for mode, route in item.get("routes", {}).items()},
        disposition=item["disposition"], evidence=item.get("evidence", []), known_defect=item.get("known_defect"),
        protected_controls=item.get("protected_controls", []), package_ownership=item.get("package_ownership"),
        candidate_profile=item.get("candidate_profile"), readiness_evidence=item.get("readiness_evidence", []),
        next_action=item.get("next_action", ""), reconciliation=item.get("reconciliation", {}),
    ) for item in data]


def _render(card: dict[str, object], lookup: dict[str, GarmentRecord]) -> str:
    records = [lookup[identity] for identity in card["record_identities"]]
    source = records[0].source_module
    lines = [
        f"# {card['card_id']} — {source['name']} {card['effective_slot']} {card['body_family']}",
        "",
        "## Status",
        "",
        "`NOT RUN`. This card is an offline-generated bounded gameplay queue, not proof of route selection, visual fit, collision clearance, or save/reload behavior.",
        "",
        "## Dependency and startup gate",
        "",
        "- Require the runtime and source-module dependencies declared by the selected local profile only after installed metadata has been re-verified.",
        f"- Candidate package ownership: `{json.dumps(card['package_ownership'], sort_keys=True)}`.",
        f"- Candidate profile: `{json.dumps(card['candidate_profile'], sort_keys=True)}`.",
        f"- Class contract: topology `{card['topology_family']}`, component `{card['component_contract']}`, mechanism `{card['defect_mechanism']}`.",
        "- Require exactly this candidate profile; do not combine mutually exclusive TEST providers.",
        "- In a playable world, record startup evidence and run `!cm_visdump` after equipping each item. A wrong observed source/target route is `INVALID PROFILE`.",
        "",
        "## Procedure",
        "",
        "For each row: execute the exact spawn command, equip the item, test Vanilla/SBBF/BCB independently where the provider supports the route, capture front/side/defect-region screenshots and movement evidence, then save/reload once. Use only `PASS`, `FAIL`, `UNCLEAR`, or `INVALID PROFILE` in results. Do not claim `collision_free` without explicit calculation or matched gameplay evidence.",
        "",
        "| Concrete identity | Root template | Stats | Source VR/path | Vanilla/SBBF/BCB target VR/path | Exact spawn command | Protected control / defect note | Result |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for record in records:
        command = f'Osi.TemplateAddTo("{record.root_template_uuid}", Osi.GetHostCharacter(), 1, 0)'
        targets = "; ".join(f"{mode}: {record.routes[mode].visual_resource_uuid} / {record.routes[mode].path}" for mode in ("Vanilla", "SBBF", "BCB"))
        protected = "; ".join(record.protected_controls) or "None recorded; preserve source-native route until tested."
        if record.known_defect:
            protected = f"{protected} Defect: {record.known_defect}"
        lines.append(f"| `{record.identity}` | `{record.root_template_uuid}` | `{record.stats_entry}` | `{record.source_visual_resource_uuid}` / `{record.source_visual_resource_path}` | {targets} | `{command}` | {protected} | NOT RUN |")
    lines.extend(["", "## Rollback and evidence", "", "If any route or visual gate fails, stop this card, retain screenshots/visdump/startup/save evidence, preserve the source route, and return the record to `DEFERRED WITH CAUSE`. Do not mutate an `ACCEPTED / PROTECT` record.", ""])
    return "\n".join(lines)


def publish_cards(cards: list[dict[str, object]], lookup: dict[str, GarmentRecord], card_dir: Path) -> None:
    """Replace exactly the generated Q-card delivery set; obsolete Q cards cannot survive regeneration."""
    from .configuration import validate_generated_outputs
    validate_generated_outputs(LocalConfiguration(Path("."), Path("."), card_dir, card_dir))
    card_dir.mkdir(parents=True, exist_ok=True)
    for existing in card_dir.glob("Q*.md"):
        existing.unlink()
    for card in cards:
        (card_dir / f"{card['card_id']}.md").write_text(_render(card, lookup), encoding="utf-8")


def main(configuration: LocalConfiguration | None = None) -> None:
    """Render cards only for a caller-selected local evidence directory."""
    config = validate_generated_outputs(configuration or load_local_configuration())
    data = json.loads((config.evidence_dir / "SCO_SINDAE_MASTER_GARMENT_LEDGER.json").read_text(encoding="utf-8"))
    records = _records_from_json(data)
    cards = bounded_cards(records)
    lookup = {record.identity: record for record in records}
    publish_cards(cards, lookup, config.card_dir)
    (config.evidence_dir / "CLASS_TEST_CARDS.json").write_text(json.dumps(cards, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()

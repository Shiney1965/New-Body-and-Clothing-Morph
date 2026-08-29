from pathlib import Path
import re

try:
    from .models import SlotResolution, StatRecord
except ImportError:  # Direct script execution from this directory only.
    from models import SlotResolution, StatRecord


ENTRY_PATTERN = re.compile(r'^new entry "([^"]+)"$')
USING_PATTERN = re.compile(r'^using "([^"]+)"$')
SLOT_PATTERN = re.compile(r'^data "Slot" "([^"]+)"$')


def parse_stats(path: str | Path) -> dict[str, StatRecord]:
    """Parse the entry, using, and Slot fields needed for strict resolution."""

    records: dict[str, StatRecord] = {}
    current_name: str | None = None
    current_using: str | None = None
    current_slot: str | None = None

    def save_current() -> None:
        if current_name is not None:
            records[current_name] = StatRecord(
                name=current_name,
                using=current_using,
                slot=current_slot,
            )

    for raw_line in Path(path).read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        entry_match = ENTRY_PATTERN.match(line)
        if entry_match:
            save_current()
            current_name = entry_match.group(1)
            current_using = None
            current_slot = None
            continue
        if current_name is None:
            continue
        using_match = USING_PATTERN.match(line)
        if using_match:
            current_using = using_match.group(1)
            continue
        slot_match = SLOT_PATTERN.match(line)
        if slot_match:
            current_slot = slot_match.group(1)
    save_current()
    return records


def resolve_slot(
    stats_name: str, stats: dict[str, StatRecord]
) -> SlotResolution:
    """Resolve a Slot only through declared `using` inheritance."""

    chain: list[str] = []
    seen: set[str] = set()
    current = stats_name
    while current:
        if current in seen:
            return SlotResolution(None, tuple(chain + [current]), cycle=True)
        seen.add(current)
        chain.append(current)
        record = stats.get(current)
        if record is None:
            return SlotResolution(None, tuple(chain), missing_parent=current)
        if record.slot is not None:
            return SlotResolution(record.slot, tuple(chain))
        current = record.using
    return SlotResolution(None, tuple(chain))

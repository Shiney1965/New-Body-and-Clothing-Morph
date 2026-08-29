from dataclasses import dataclass


@dataclass(frozen=True)
class StatRecord:
    name: str
    using: str | None = None
    slot: str | None = None


@dataclass(frozen=True)
class SlotResolution:
    slot: str | None
    inheritance: tuple[str, ...]
    cycle: bool = False
    missing_parent: str | None = None

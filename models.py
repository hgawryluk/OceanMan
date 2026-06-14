from dataclasses import dataclass, field
from datetime import date, datetime


@dataclass
class SlotReading:
    pool: str
    weekday: str        # "monday" … "sunday"
    slot_start: str     # "07:00"
    slot_end: str       # "07:30"
    free_lanes: int
    total_lanes: int


@dataclass
class PoolSchedule:
    pool: str
    valid_from: date | None
    fetched_at: datetime
    source_url: str
    source_hash: str
    slots: list[SlotReading] = field(default_factory=list)

"""Deterministic monthly seasons anchored at 2026-09-01 (Season 001)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

SEASON_EPOCH = date(2026, 9, 1)
SEASONS = (
    {"flower": "Rose", "color": "#e11d48"},
    {"flower": "Sunflower", "color": "#ca8a04"},
    {"flower": "Lavender", "color": "#7c3aed"},
    {"flower": "Cornflower", "color": "#2563eb"},
    {"flower": "Poppy", "color": "#ff4b26"},
    {"flower": "Forget-me-not", "color": "#0ea5e9"},
    {"flower": "Lilac", "color": "#a21caf"},
    {"flower": "Marigold", "color": "#ea5808"},
    {"flower": "Hydrangea", "color": "#0d9488"},
    {"flower": "Peony", "color": "#db2777"},
)


@dataclass(frozen=True)
class Season:
    num: int
    start: date
    end: date
    next_start: date
    flower: str
    color: str

    def to_payload(self, timezone_name: str) -> dict[str, str | int]:
        return {
            "num": self.num,
            "number": self.num,
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
            "flower": self.flower,
            "color": self.color,
            "timezone_name": timezone_name,
        }


def local_date(timezone_name: str | None = "UTC", now: datetime | None = None) -> date:
    """Current date in the given IANA timezone; invalid values safely use UTC."""
    try:
        zone = ZoneInfo(timezone_name or "UTC")
    except (ZoneInfoNotFoundError, TypeError, ValueError):
        zone = ZoneInfo("UTC")
    moment = now or datetime.now(timezone.utc)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(zone).date()


def season_for_date(day: date) -> Season:
    """Return the monthly season containing day; Sep 2026 is Season 001."""
    number = (day.year - SEASON_EPOCH.year) * 12 + day.month - SEASON_EPOCH.month + 1
    start = date(day.year, day.month, 1)
    if day.month == 12:
        next_start = date(day.year + 1, 1, 1)
    else:
        next_start = date(day.year, day.month + 1, 1)
    flower = SEASONS[number % len(SEASONS)]
    return Season(
        num=number,
        start=start,
        end=next_start - timedelta(days=1),
        next_start=next_start,
        flower=flower["flower"],
        color=flower["color"],
    )


def current_season(timezone_name: str | None = "UTC", now: datetime | None = None) -> Season:
    """Return the season for the user's local calendar date."""
    return season_for_date(local_date(timezone_name, now=now))

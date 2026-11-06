"""Business-local time. Datetimes are stored naive in the business's timezone."""

from datetime import date, datetime
from zoneinfo import ZoneInfo

_frozen: datetime | None = None  # tests can freeze the clock


def freeze(value: datetime | None) -> None:
    global _frozen
    _frozen = value


DEFAULT_TZ = "Asia/Kolkata"


def now(tz: str | None = DEFAULT_TZ) -> datetime:
    if _frozen is not None:
        return _frozen
    return datetime.now(ZoneInfo(tz or DEFAULT_TZ)).replace(tzinfo=None, second=0, microsecond=0)


def today(tz: str | None = DEFAULT_TZ) -> date:
    return now(tz).date()


FMT = "%Y-%m-%d %H:%M"
WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def speakable(dt: datetime) -> str:
    return dt.strftime("%A %d %B, %I:%M %p")

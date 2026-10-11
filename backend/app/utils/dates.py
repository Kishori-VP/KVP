"""Date helpers.

Conventions:
- Timestamps (created_at, submitted_at, ...) are stored as UTC datetimes.
- Calendar dates (visit_date, period_start, dob, ...) are stored as UTC-midnight
  datetimes, because MongoDB has no date-only type.
- "Today" is evaluated in the programme timezone (Asia/Kolkata by default).
"""

import calendar
from datetime import UTC, date, datetime, time, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

from app.core.config import settings

PeriodType = Literal["daily", "weekly", "monthly", "quarterly", "yearly", "custom"]


def utcnow() -> datetime:
    return datetime.now(UTC)


def local_tz() -> ZoneInfo:
    return ZoneInfo(settings.timezone)


def today_local() -> date:
    return datetime.now(local_tz()).date()


def to_dt(d: date | datetime | None) -> datetime | None:
    """Convert a calendar date to the UTC-midnight datetime used for storage."""
    if d is None:
        return None
    if isinstance(d, datetime):
        if d.tzinfo is None:
            return d.replace(tzinfo=UTC)
        return d
    return datetime.combine(d, time.min, tzinfo=UTC)


def to_date(d: date | datetime | None) -> date | None:
    if d is None:
        return None
    if isinstance(d, datetime):
        return d.date()
    return d


def day_range(start: date, end: date) -> tuple[datetime, datetime]:
    """Inclusive date range -> [start 00:00, end+1 00:00) datetimes for queries."""
    return to_dt(start), to_dt(end + timedelta(days=1))


def period_bounds(period: PeriodType, ref: date | None = None) -> tuple[date, date]:
    """Return inclusive (start, end) dates of the period containing `ref`.

    Quarters and years follow the programme year, which starts in July
    (KVP calendar runs July -> June).
    """
    ref = ref or today_local()
    if period == "daily":
        return ref, ref
    if period == "weekly":
        start = ref - timedelta(days=ref.weekday())
        return start, start + timedelta(days=6)
    if period == "monthly":
        last = calendar.monthrange(ref.year, ref.month)[1]
        return ref.replace(day=1), ref.replace(day=last)
    if period == "quarterly":
        # Programme quarters: Jul-Sep, Oct-Dec, Jan-Mar, Apr-Jun (calendar quarters).
        q_start_month = 3 * ((ref.month - 1) // 3) + 1
        start = date(ref.year, q_start_month, 1)
        end_month = q_start_month + 2
        end = date(ref.year, end_month, calendar.monthrange(ref.year, end_month)[1])
        return start, end
    if period == "yearly":
        start_year = ref.year if ref.month >= 7 else ref.year - 1
        return date(start_year, 7, 1), date(start_year + 1, 6, 30)
    raise ValueError("custom periods need explicit start and end dates")


def previous_period(period: PeriodType, start: date) -> tuple[date, date]:
    return period_bounds(period, start - timedelta(days=1))


def next_period(period: PeriodType, end: date) -> tuple[date, date]:
    return period_bounds(period, end + timedelta(days=1))


def age_on(dob: date, on: date) -> int:
    return on.year - dob.year - ((on.month, on.day) < (dob.month, dob.day))

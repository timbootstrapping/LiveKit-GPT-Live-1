"""Cal.com calendar tools for the Northside Dental agent.

With GPT-Live and `responses` delegation, the backend model calls these tools and
they run in the agent process. Credentials come from the environment
(CAL_API_KEY, CAL_EVENT_TYPE_ID, CAL_TIMEZONE) and are never logged.
"""

import asyncio
import logging
import os
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

import aiohttp
from livekit.agents import RunContext, function_tool, utils
from livekit.agents.llm import ToolError

logger = logging.getLogger("cal_tools")

CAL_API_BASE = "https://api.cal.com/v2"
# Each Cal.com v2 endpoint has its own version header, taken from its reference page
SLOTS_API_VERSION = "2024-09-04"
BOOKINGS_API_VERSION = "2026-02-25"

REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=10)
MAX_SLOTS = 5
MAX_SLOTS_PER_DAY = 2

_HOURS = [
    "twelve", "one", "two", "three", "four", "five",
    "six", "seven", "eight", "nine", "ten", "eleven",
]  # fmt: skip
_ONES = [
    "", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine",
    "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen",
    "seventeen", "eighteen", "nineteen",
]  # fmt: skip
_TENS = ["", "", "twenty", "thirty", "forty", "fifty"]


def business_timezone() -> ZoneInfo:
    return ZoneInfo(os.environ.get("CAL_TIMEZONE") or "Europe/Berlin")


def current_datetime_context() -> str:
    """A sentence with today's date, weekday and time in the business timezone."""
    tz = business_timezone()
    now = datetime.now(tz)
    return (
        f"Today is {now:%A}, {now.day} {now:%B %Y} ({now:%Y-%m-%d}), "
        f"and the current time is {now:%H:%M} in {tz.key}."
    )


def _config() -> tuple[str, int]:
    api_key = os.environ.get("CAL_API_KEY")
    event_type_id = os.environ.get("CAL_EVENT_TYPE_ID")
    if not api_key or not event_type_id or not event_type_id.isdigit():
        logger.error("CAL_API_KEY or CAL_EVENT_TYPE_ID is missing or invalid")
        raise ToolError("The calendar isn't available right now.")
    return api_key, int(event_type_id)


def _utc_iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_iso(value: str) -> datetime:
    # Python 3.10 doesn't accept a trailing "Z"
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _ordinal(n: int) -> str:
    suffix = (
        "th" if 11 <= n % 100 <= 13 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    )
    return f"{n}{suffix}"


def _spoken_day(dt: datetime) -> str:
    return f"{dt:%A} the {_ordinal(dt.day)} of {dt:%B}"


def _spoken_minutes(m: int) -> str:
    if m < 10:
        return f"oh {_ONES[m]}"
    if m < 20:
        return _ONES[m]
    return f"{_TENS[m // 10]} {_ONES[m % 10]}".strip()


def _spoken_clock(dt: datetime) -> str:
    hour, minute = _HOURS[dt.hour % 12], dt.minute
    if minute == 0:
        return hour
    if minute == 15:
        return f"quarter past {hour}"
    if minute == 30:
        return f"half past {hour}"
    if minute == 45:
        return f"quarter to {_HOURS[(dt.hour + 1) % 12]}"
    return f"{hour} {_spoken_minutes(minute)}"


def _period(dt: datetime) -> str:
    if dt.hour < 12:
        return "in the morning"
    if dt.hour < 17:
        return "in the afternoon"
    return "in the evening"


def _join(parts: list[str], sep: str = " and ") -> str:
    if len(parts) <= 1:
        return "".join(parts)
    return f"{', '.join(parts[:-1])}{sep}{parts[-1]}"


def _spoken_times(slots: list[datetime]) -> str:
    """e.g. "ten and half past eleven in the morning, and two in the afternoon"."""
    groups: list[tuple[str, list[str]]] = []
    for dt in slots:
        if groups and groups[-1][0] == _period(dt):
            groups[-1][1].append(_spoken_clock(dt))
        else:
            groups.append((_period(dt), [_spoken_clock(dt)]))
    return _join([f"{_join(times)} {period}" for period, times in groups], ", and ")


def _parse_day(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise ToolError(f"'{value}' isn't a date in the form YYYY-MM-DD.") from None


@function_tool()
async def check_availability(
    context: RunContext, start_date: str, end_date: str
) -> str:
    """Find open appointment times at Northside Dental between two dates.

    Always call this before offering the caller any times, and only offer times it
    returns. Returns a short spoken sentence with a handful of open times in the
    practice's local time.

    Args:
        start_date: First day to search, in the practice's local time, as YYYY-MM-DD.
        end_date: Last day to search (inclusive), as YYYY-MM-DD. Use the same date as start_date for a single day.
    """
    api_key, event_type_id = _config()
    tz = business_timezone()
    start_day, end_day = _parse_day(start_date), _parse_day(end_date)
    if end_day < start_day:
        raise ToolError("The end date is before the start date.")

    # Cal.com wants the range in UTC; cover the whole local days
    params = {
        "eventTypeId": str(event_type_id),
        "start": _utc_iso(datetime.combine(start_day, time.min, tz)),
        "end": _utc_iso(datetime.combine(end_day, time(23, 59, 59), tz)),
        "timeZone": tz.key,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "cal-api-version": SLOTS_API_VERSION,
    }

    try:
        session = utils.http_context.http_session()
        async with session.get(
            f"{CAL_API_BASE}/slots",
            params=params,
            headers=headers,
            timeout=REQUEST_TIMEOUT,
        ) as resp:
            if resp.status != 200:
                logger.warning(
                    "Cal.com slots request failed with status %s", resp.status
                )
                raise ToolError("I couldn't check the calendar just now.")
            body = await resp.json()
    except (aiohttp.ClientError, asyncio.TimeoutError):
        logger.warning("Cal.com slots request could not be completed", exc_info=True)
        raise ToolError("I couldn't reach the calendar just now.") from None

    now = datetime.now(tz)
    per_day: dict[date, list[datetime]] = {}
    for day_slots in (body.get("data") or {}).values():
        for slot in day_slots:
            raw = slot["start"] if isinstance(slot, dict) else slot
            dt = _parse_iso(raw).astimezone(tz)
            if dt > now:
                per_day.setdefault(dt.date(), []).append(dt)

    chosen: list[datetime] = []
    for day in sorted(per_day):
        chosen.extend(sorted(per_day[day])[:MAX_SLOTS_PER_DAY])
    chosen = chosen[:MAX_SLOTS]

    if not chosen:
        if start_day == end_day:
            return f"There are no open times on {_spoken_day(datetime.combine(start_day, time.min, tz))}."
        return (
            f"There are no open times between "
            f"{_spoken_day(datetime.combine(start_day, time.min, tz))} and "
            f"{_spoken_day(datetime.combine(end_day, time.min, tz))}."
        )

    days: list[str] = []
    for day in sorted({dt.date() for dt in chosen}):
        slots = [dt for dt in chosen if dt.date() == day]
        days.append(f"{_spoken_day(slots[0])} at {_spoken_times(slots)}")
    return f"Open times are {'; '.join(days)}."


@function_tool()
async def book_appointment(
    context: RunContext, start_time: str, full_name: str, email: str
) -> str:
    """Book an appointment at Northside Dental.

    Only call this after check_availability has shown the time as open, and after
    the caller has confirmed their full name, their email address and the exact
    time. Returns a short spoken confirmation.

    Args:
        start_time: Appointment start in the practice's local time, 24-hour, as YYYY-MM-DDTHH:MM (for example 2026-10-06T14:30).
        full_name: The caller's full name, first and last.
        email: The caller's email address, as confirmed with them.
    """
    api_key, event_type_id = _config()
    tz = business_timezone()

    try:
        start = datetime.fromisoformat(start_time)
    except ValueError:
        raise ToolError(
            f"'{start_time}' isn't a time in the form YYYY-MM-DDTHH:MM."
        ) from None
    start = start.replace(tzinfo=tz) if start.tzinfo is None else start.astimezone(tz)
    if start <= datetime.now(tz) + timedelta(minutes=1):
        raise ToolError("That time has already passed. Offer the caller a later time.")

    email = email.strip()
    local, _, domain = email.partition("@")
    if not local or "." not in domain:
        raise ToolError(
            "That email address doesn't look complete. Ask the caller to spell it again."
        )

    payload = {
        # Cal.com wants the start in UTC, plus the attendee's timezone
        "start": _utc_iso(start),
        "eventTypeId": event_type_id,
        "attendee": {
            "name": full_name.strip(),
            "email": email,
            "timeZone": tz.key,
        },
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "cal-api-version": BOOKINGS_API_VERSION,
    }

    try:
        session = utils.http_context.http_session()
        async with session.post(
            f"{CAL_API_BASE}/bookings",
            json=payload,
            headers=headers,
            timeout=REQUEST_TIMEOUT,
        ) as resp:
            if resp.status not in (200, 201):
                logger.warning("Cal.com booking failed with status %s", resp.status)
                raise ToolError(
                    "The booking didn't go through, most likely because that time "
                    "was just taken. Check availability again and offer the caller "
                    "another time."
                )
    except (aiohttp.ClientError, asyncio.TimeoutError):
        logger.warning("Cal.com booking request could not be completed", exc_info=True)
        raise ToolError(
            "I couldn't reach the calendar to book that. Ask the caller if they'd "
            "like to try again."
        ) from None

    return (
        f"Booked. {full_name.strip()} is confirmed for {_spoken_day(start)} "
        f"at {_spoken_clock(start)} {_period(start)}. "
        f"A confirmation email is on its way to {email}."
    )


TOOLS = [check_availability, book_appointment]

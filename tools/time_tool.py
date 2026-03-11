from __future__ import annotations

import logging
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

logger = logging.getLogger(__name__)

# Common abbreviation aliases not in the IANA database
_ALIASES = {
    "EST": "America/New_York",
    "EDT": "America/New_York",
    "CST": "America/Chicago",
    "CDT": "America/Chicago",
    "MST": "America/Denver",
    "MDT": "America/Denver",
    "PST": "America/Los_Angeles",
    "PDT": "America/Los_Angeles",
    "GMT": "UTC",
    "IST": "Asia/Kolkata",
    "JST": "Asia/Tokyo",
    "KST": "Asia/Seoul",
    "CET": "Europe/Paris",
    "CEST": "Europe/Paris",
    "AEST": "Australia/Sydney",
    "AEDT": "Australia/Sydney",
    "BST": "Europe/London",
}


async def get_current_time(timezone: str = "UTC") -> str:
    """Get the current date and time in any timezone."""
    tz_name = timezone.strip()
    try:
        tz = ZoneInfo(tz_name)
    except ZoneInfoNotFoundError:
        alias = _ALIASES.get(tz_name.upper())
        if alias:
            tz = ZoneInfo(alias)
        else:
            return (
                f"Unknown timezone: '{tz_name}'. "
                "Use IANA format like 'America/New_York', 'Europe/London', 'Asia/Tokyo', or 'UTC'."
            )
    except Exception as e:
        return f"Error getting time for '{tz_name}': {e}"

    now = datetime.now(tz)
    return f"Current time in {tz_name}: {now.strftime('%A, %Y-%m-%d %H:%M:%S %Z')}"


def make_time_tool() -> dict:
    return {"name": "get_current_time", "fn": get_current_time}

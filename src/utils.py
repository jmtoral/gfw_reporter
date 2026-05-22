from datetime import datetime


def ordinal_day(day: int) -> str:
    if 10 <= day % 100 <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")
    return f"{day}{suffix}"


def format_event_date(value) -> str:
    """Format a date as YYYY-MM-DD (Month 1st, YYYY) when possible."""
    if value is None:
        return "Unknown date"

    if isinstance(value, datetime):
        dt = value
    else:
        raw = str(value).strip()
        if not raw or raw.lower() == "nan":
            return "Unknown date"

        dt = None
        for pattern in ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%m/%d/%Y", "%d/%m/%Y", "%Y/%m/%d"):
            try:
                dt = datetime.strptime(raw, pattern)
                break
            except ValueError:
                continue

        if dt is None:
            try:
                dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            except ValueError:
                return raw

    iso_date = dt.strftime("%Y-%m-%d")
    human_date = f"{dt.strftime('%B')} {ordinal_day(dt.day)}, {dt.year}"
    return f"{iso_date} ({human_date})"

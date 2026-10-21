"""Date helpers shared by appointments and expenses."""

from datetime import date, datetime


def today():
    # Called as dates.today() everywhere so tests can pin the date in one place.
    return date.today()


def check_date(raw, label="Date"):
    """Return (value, error). A valid date comes back canonical (YYYY-MM-DD) because
    code sorts and filters dates as strings; an invalid one comes back as typed."""
    value = raw.strip()
    if not value:
        return value, f"{label} is required."
    try:
        parsed = datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        return value, "Enter a valid date (YYYY-MM-DD)."
    if not 2000 <= parsed.year <= 2100:
        return value, "Enter a date between 2000 and 2100."
    return parsed.strftime("%Y-%m-%d"), None

# core/date_utils.py - Plain Python date conversion and normalization utilities.
# Converts relative labels ('Today', 'Tomorrow', 'Tuesday', 'Dec 3') into standard DD-MM-YYYY dates
# based on the computer's system clock, without external services.

import datetime
import re
from typing import List, Optional
from models.schemas import Row
from utils.logger import logger

MONTH_MAP = {
    "jan": 1, "january": 1,
    "feb": 2, "february": 2,
    "mar": 3, "march": 3,
    "apr": 4, "april": 4,
    "may": 5,
    "jun": 6, "june": 6,
    "jul": 7, "july": 7,
    "aug": 8, "august": 8,
    "sep": 9, "september": 9, "sept": 9,
    "oct": 10, "october": 10,
    "nov": 11, "november": 11,
    "dec": 12, "december": 12,
}

WEEKDAY_MAP = {
    "monday": 0, "mon": 0,
    "tuesday": 1, "tue": 1, "tues": 1,
    "wednesday": 2, "wed": 2,
    "thursday": 3, "thu": 3, "thur": 3, "thurs": 3,
    "friday": 4, "fri": 4,
    "saturday": 5, "sat": 5,
    "sunday": 6, "sun": 6,
}


def parse_date_label(raw_label: str, reference_date: Optional[datetime.date] = None) -> str:
    """
    Converts a date label to DD-MM-YYYY format using a reference date (defaults to today).
    
    Args:
        raw_label: Extracted date label string (e.g. 'Today', 'Tomorrow', 'Dec 3', 'Tuesday').
        reference_date: Base calendar date to anchor relative dates (defaults to today).
        
    Returns:
        str: Date formatted as DD-MM-YYYY, or the original label if it cannot be converted.
    """
    if not raw_label:
        return raw_label

    cleaned = raw_label.strip()
    lower = cleaned.lower()

    if lower in ("not found", "none", "null", "tbd", "n/a"):
        return cleaned

    base = reference_date or datetime.date.today()

    # 0. Check if already formatted as DD-MM-YYYY
    match_already = re.match(r"^(\d{2})-(\d{2})-(\d{4})$", cleaned)
    if match_already:
        return cleaned

    # 0.1 Check for ISO date format (YYYY-MM-DD or YYYY-MM-DDTHH:MM...)
    match_iso = re.search(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b", cleaned)
    if match_iso:
        y, m, d = int(match_iso.group(1)), int(match_iso.group(2)), int(match_iso.group(3))
        try:
            target = datetime.date(y, m, d)
            return target.strftime("%d-%m-%Y")
        except ValueError:
            pass

    # 1. Handle "Today", "Tomorrow", "Yesterday"
    if lower == "today" or lower.startswith("today"):
        return base.strftime("%d-%m-%Y")
    if lower == "tomorrow" or lower.startswith("tomorrow"):
        return (base + datetime.timedelta(days=1)).strftime("%d-%m-%Y")
    if lower == "yesterday" or lower.startswith("yesterday"):
        return (base - datetime.timedelta(days=1)).strftime("%d-%m-%Y")

    # 2. Check for month name and day number (e.g. "Dec 3", "3 Dec", "December 24", "Nov 26")
    # Matches "Dec 3" or "Dec 03"
    match_month_first = re.search(r"\b([a-zA-Z]{3,9})\s+(\d{1,2})\b", cleaned)
    # Matches "3 Dec" or "26 Nov"
    match_day_first = re.search(r"\b(\d{1,2})\s+([a-zA-Z]{3,9})\b", cleaned)

    month_name, day_str = None, None
    if match_month_first and match_month_first.group(1).lower() in MONTH_MAP:
        month_name = match_month_first.group(1).lower()
        day_str = match_month_first.group(2)
    elif match_day_first and match_day_first.group(2).lower() in MONTH_MAP:
        month_name = match_day_first.group(2).lower()
        day_str = match_day_first.group(1)

    if month_name and day_str:
        month = MONTH_MAP[month_name]
        day = int(day_str)
        # Determine year: if target month is before current month, assume next year
        year = base.year
        if month < base.month or (month == base.month and day < base.day):
            # If the event is in January/February and we are in November/December, rollover to next year
            if base.month >= 10 and month <= 3:
                year += 1
        try:
            target = datetime.date(year, month, day)
            return target.strftime("%d-%m-%Y")
        except ValueError:
            pass

    # 3. Check for standalone weekday name (e.g. "Tuesday", "Thursday")
    for w_name, w_idx in WEEKDAY_MAP.items():
        if re.search(rf"\b{w_name}\b", lower):
            days_ahead = (w_idx - base.weekday()) % 7
            target = base + datetime.timedelta(days=days_ahead)
            return target.strftime("%d-%m-%Y")

    # If label cannot be parsed, return original text unchanged
    return cleaned


def standardize_row_dates(
    rows: List[Row],
    date_column: str = "Date",
    reference_date: Optional[datetime.date] = None,
) -> List[Row]:
    """
    Standardizes the date column in all rows to DD-MM-YYYY format.
    
    Args:
        rows: Extracted rows.
        date_column: The name of the date column.
        reference_date: Optional reference date (defaults to today).
        
    Returns:
        List[Row]: Rows with converted date strings.
    """
    ref = reference_date or datetime.date.today()
    for row in rows:
        if date_column in row.data:
            original = str(row.data[date_column])
            standardized = parse_date_label(original, reference_date=ref)
            row.data[date_column] = standardized

    logger.info(f"Standardized dates across {len(rows)} rows using reference {ref:%d-%m-%Y}.")
    return rows


def format_time_24h(raw_time: str) -> str:
    """
    Converts 12-hour clock times (e.g. '5:30 PM', '12:30 PM', '12:00 AM')
    to 24-hour HH:MM format ('17:30', '12:30', '00:00').
    Leaves existing 24-hour times ('17:00') intact.
    If the value is not a clock time, returns it unchanged.
    
    Args:
        raw_time: Raw time string.
        
    Returns:
        str: 24-hour formatted time (HH:MM) or original string.
    """
    if not raw_time:
        return raw_time

    cleaned = raw_time.strip()
    lower = cleaned.lower()

    if lower in ("not found", "none", "null", "tbd", "n/a"):
        return cleaned

    # 1. Match 12-hour time: HH:MM AM/PM or H:MM AM/PM
    match_12h = re.match(r"^(\d{1,2}):(\d{2})\s*(am|pm|a\.m\.|p\.m\.)$", cleaned, re.IGNORECASE)
    if match_12h:
        hours = int(match_12h.group(1))
        minutes = int(match_12h.group(2))
        meridian = match_12h.group(3).lower().replace(".", "")
        if 1 <= hours <= 12 and 0 <= minutes <= 59:
            if meridian == "pm" and hours != 12:
                hours += 12
            elif meridian == "am" and hours == 12:
                hours = 0
            return f"{hours:02d}:{minutes:02d}"

    # 2. Match 12-hour time without minutes: e.g. "5 PM", "12 AM"
    match_12h_no_min = re.match(r"^(\d{1,2})\s*(am|pm|a\.m\.|p\.m\.)$", cleaned, re.IGNORECASE)
    if match_12h_no_min:
        hours = int(match_12h_no_min.group(1))
        meridian = match_12h_no_min.group(2).lower().replace(".", "")
        if 1 <= hours <= 12:
            if meridian == "pm" and hours != 12:
                hours += 12
            elif meridian == "am" and hours == 12:
                hours = 0
            return f"{hours:02d}:00"

    # 3. Match 24-hour time: e.g. "17:00", "09:30", "9:30"
    match_24h = re.match(r"^(\d{1,2}):(\d{2})$", cleaned)
    if match_24h:
        hours = int(match_24h.group(1))
        minutes = int(match_24h.group(2))
        if 0 <= hours <= 23 and 0 <= minutes <= 59:
            return f"{hours:02d}:{minutes:02d}"

    return cleaned


def clean_host_name(raw_host: str) -> str:
    """
    Removes leading 'By ' prefix from host names (e.g. 'By BOX SF' -> 'BOX SF').
    
    Args:
        raw_host: Raw host name string.
        
    Returns:
        str: Host name without leading 'By '.
    """
    if not raw_host:
        return raw_host
    cleaned = raw_host.strip()
    if cleaned.lower().startswith("by "):
        return cleaned[3:].strip()
    return cleaned


def standardize_row_times(rows: List[Row], time_column: str = "Time") -> List[Row]:
    """
    Standardizes the time column in all rows to 24-hour HH:MM format.
    """
    for row in rows:
        if time_column in row.data:
            original = str(row.data[time_column])
            row.data[time_column] = format_time_24h(original)
    return rows


def standardize_row_hosts(rows: List[Row], host_column: str = "Host") -> List[Row]:
    """
    Removes leading 'By ' from host names across all rows.
    """
    for row in rows:
        if host_column in row.data:
            original = str(row.data[host_column])
            row.data[host_column] = clean_host_name(original)
    return rows


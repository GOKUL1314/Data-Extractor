# core/field_detectors.py - Deterministic regex and positional field detectors.
# Extracts dates, clock times, URLs, prices, points, comments, hosts, and locations
# from HTML elements and raw text strings deterministically.

import re
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin
from bs4 import NavigableString, Tag

# Regex patterns for field detection
DATE_PATTERNS = [
    # Relative terms
    r"\b(?:today|tomorrow|yesterday)\b",
    # Weekdays
    r"\b(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday|mon|tue|wed|thu|fri|sat|sun)\b",
    # Month Day (e.g. Nov 24, November 24, 24 Nov, 24 November, Nov 24, 2026)
    r"\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+\d{1,2}(?:st|nd|rd|th)?(?:,?\s+\d{4})?\b",
    r"\b\d{1,2}(?:st|nd|rd|th)?\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?(?:,?\s+\d{4})?\b",
    # Numeric dates (YYYY-MM-DD, DD-MM-YYYY, DD/MM/YYYY)
    r"\b\d{4}-\d{1,2}-\d{1,2}\b",
    r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b",
]

TIME_PATTERNS = [
    # 12-hour or 24-hour clock time (e.g., 5:30 PM, 17:00, 12:30pm, 9 AM)
    r"\b\d{1,2}:\d{2}\s*(?:[aApP]\.?[mM]\.?)?\b",
    r"\b\d{1,2}\s*[aApP]\.?[mM]\.\b",
]

PRICE_PATTERNS = [
    # Currencies: $, €, £, ¥ followed by digits, or Free
    r"\$\s*[\d,]+(?:\.\d{2})?(?:\s*(?:k|K|/yr|/mo|per year|per month))?",
    r"[€£¥]\s*[\d,]+(?:\.\d{2})?",
    r"\b[\d,]+\s*(?:USD|EUR|GBP|INR)\b",
    r"\b(?:free|free admission|free ticket)\b",
]

POINTS_PATTERN = r"\b(\d+)\s*(?:points?|pts?|upvotes?)\b"
COMMENTS_PATTERN = r"\b(\d+)\s*(?:comments?|discuss)\b"
HOST_PREFIX_PATTERN = r"^(?:by|hosted by|organizer:?|author:?|company:?)\s+(.*)"


def detect_date(text: str) -> Optional[str]:
    """Finds and returns a date string within the given text."""
    if not text:
        return None
    for pattern in DATE_PATTERNS:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(0).strip()
    return None


def detect_time(text: str) -> Optional[str]:
    """Finds and returns a clock time string (e.g. '17:00', '5:30 PM') within text."""
    if not text:
        return None
    for pattern in TIME_PATTERNS:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(0).strip()
    return None


def detect_price(text: str) -> Optional[str]:
    """Finds and returns a price or compensation string within text."""
    if not text:
        return None
    for pattern in PRICE_PATTERNS:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(0).strip()
    return None


def detect_points(text: str) -> Optional[str]:
    """Finds score or point count (e.g. '150 points' -> '150')."""
    if not text:
        return None
    match = re.search(POINTS_PATTERN, text, re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return None


def detect_comments(text: str) -> Optional[str]:
    """Finds comment count (e.g. '42 comments' -> '42')."""
    if not text:
        return None
    match = re.search(COMMENTS_PATTERN, text, re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return None


def detect_host(line: str) -> Optional[str]:
    """Extracts host/author if the line starts with 'By ', 'Hosted by ', etc."""
    if not line:
        return None
    match = re.match(HOST_PREFIX_PATTERN, line.strip(), re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return None


def detect_location(text: str) -> Optional[str]:
    """Finds location candidate string."""
    if not text:
        return None
    cleaned = text.strip()
    if 2 <= len(cleaned) <= 60 and not detect_time(cleaned) and not detect_date(cleaned) and not detect_host(cleaned):
        return cleaned
    return None


def extract_fields_from_dom_node(
    node: Tag,
    base_url: str,
    inherited_date: Optional[str] = None,
) -> Dict[str, str]:
    """
    Extracts structured fields from an HTML container element using heuristic rules.
    
    Rules applied:
    - Link: First anchor link with an href.
    - Name: Anchor aria-label, heading tag (h1-h6), or first prominent link text.
    - Host: Line starting with 'By', or element with host/company in class.
    - Date: Extracted date token or inherited section date heading.
    - Time: Clock time token.
    - Price: Dollar / currency string.
    - Points: Upvote / points token.
    - Comments: Comments token.
    - Location: Last short text line that isn't time, date, or host.
    """
    extracted: Dict[str, str] = {}

    # 1. Link & Name from <a> tags
    links = node.find_all("a", href=True)
    if links:
        chosen_link = None
        # Prefer action link: Apply, Register, Details, etc., or specific item path
        for lk in links:
            txt_lower = lk.get_text(strip=True).lower()
            href_lower = lk["href"].lower()
            if any(k in txt_lower for k in ("apply", "register", "rsvp", "details", "view", "ticket")):
                chosen_link = lk
                break
            if any(k in href_lower for k in ("/jobs/", "/job/", "/event/", "/events/", "/p/", "/item")):
                chosen_link = lk
                break

        # If not matched, filter out generic home / site / sponsor links
        if not chosen_link:
            for lk in links:
                href = lk["href"].strip()
                if len(links) > 1 and (href in ("/", "#") or "realpython.com" in href or "twitter.com" in href or "facebook.com" in href):
                    continue
                chosen_link = lk
                break

        if not chosen_link:
            chosen_link = links[0]

        extracted["Link"] = urljoin(base_url, chosen_link["href"].strip())

        # Name heuristic: aria-label on anchor is often the cleanest full title
        aria_label = chosen_link.get("aria-label", "").strip()
        if aria_label and len(aria_label) > 2:
            extracted["Name"] = aria_label

    # If Name not found from aria-label, check headings (h1..h6)
    if "Name" not in extracted:
        heading = node.find(["h1", "h2", "h3", "h4", "h5", "h6"])
        if heading and heading.get_text(strip=True):
            extracted["Name"] = heading.get_text(strip=True)

    # If Name still not found, check elements with title/name class
    if "Name" not in extracted:
        title_tag = node.find(class_=lambda c: c and any(k in str(c).lower() for k in ("title", "headline", "name")))
        if title_tag and title_tag.get_text(strip=True):
            extracted["Name"] = title_tag.get_text(strip=True)

    # Fallback Name: first link text
    if "Name" not in extracted and first_link and first_link.get_text(strip=True):
        extracted["Name"] = first_link.get_text(strip=True)

    # 2. Check for explicit class tags for company/host or location
    company_tag = node.find(class_=lambda c: c and any(k in str(c).lower() for k in ("company", "host", "organizer", "author")))
    if company_tag and company_tag.get_text(strip=True):
        extracted["Host"] = company_tag.get_text(strip=True)

    location_tag = node.find(class_=lambda c: c and any(k in str(c).lower() for k in ("location", "venue", "city", "place")))
    if location_tag and location_tag.get_text(strip=True):
        extracted["Location"] = location_tag.get_text(strip=True)

    time_tag = node.find(class_=lambda c: c and "time" in str(c).lower())
    if time_tag and time_tag.get_text(strip=True):
        found_time = detect_time(time_tag.get_text(strip=True))
        if found_time:
            extracted["Time"] = found_time

    # 3. Extract text lines and examine individual values
    lines: List[str] = [s.strip() for s in node.stripped_strings if s.strip() and s.strip() != "\u200b"]

    short_candidates_for_location: List[str] = []

    for line in lines:
        # Check for Host with "By "
        if "Host" not in extracted:
            host_candidate = detect_host(line)
            if host_candidate:
                extracted["Host"] = host_candidate
                continue

        # Check for Time
        if "Time" not in extracted:
            t = detect_time(line)
            if t:
                extracted["Time"] = t
                continue

        # Check for Date
        if "Date" not in extracted:
            d = detect_date(line)
            if d:
                extracted["Date"] = d
                continue

        # Check for Price
        if "Price" not in extracted:
            p = detect_price(line)
            if p:
                extracted["Price"] = p
                continue

        # Check for Points
        if "Points" not in extracted:
            pts = detect_points(line)
            if pts:
                extracted["Points"] = pts
                continue

        # Check for Comments
        if "Comments" not in extracted:
            com = detect_comments(line)
            if com:
                extracted["Comments"] = com
                continue

        # Candidate for Location or secondary info (short lines, not the title)
        if len(line) <= 60 and line != extracted.get("Name"):
            short_candidates_for_location.append(line)

    # If Location not set from class, assign last short text line
    if "Location" not in extracted and short_candidates_for_location:
        # Filter out anything that matches time, date, host, points, or comments
        valid_locs = [
            c for c in short_candidates_for_location
            if not detect_time(c) and not detect_date(c) and not detect_host(c)
            and not detect_points(c) and not detect_comments(c)
            and c != extracted.get("Host")
        ]
        if valid_locs:
            extracted["Location"] = valid_locs[-1]

    # If Date still missing, inherit from parent section date heading
    if "Date" not in extracted and inherited_date:
        extracted["Date"] = inherited_date

    return extracted

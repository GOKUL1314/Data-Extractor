# core/url_handler.py - Step 1: Input URL validation, cleaning, and deduplication.
# This file takes the raw multiline string of URLs submitted by the user,
# cleans each one, validates its format, and removes duplicates.

import re
from typing import List, Optional
from urllib.parse import urlparse
from utils.logger import logger

_ZERO_WIDTH_RE = re.compile(r"[\u200b\u200c\u200d\u200e\u200f\ufeff\xa0]")


def clean_url(raw_url: str) -> Optional[str]:
    """
    Cleans and standardizes a single URL string.
    Handles invisible characters, surrounding quotes/punctuation, case-insensitive schemes,
    and prefix text before an http(s) URL.
    
    Args:
        raw_url: The raw URL string from user input.
        
    Returns:
        Optional[str]: Standardized URL with http:// or https:// protocol, or None if invalid.
    """
    if not raw_url:
        return None

    # Remove invisible Unicode whitespace/zero-width chars and outer quotes/brackets/commas
    stripped = _ZERO_WIDTH_RE.sub("", raw_url).strip()
    stripped = stripped.strip("\"'<>[](),;")
    if not stripped:
        return None

    # If text contains an explicit http:// or https:// URL (e.g. "url: Https://luma.com/sf"), extract it
    url_match = re.search(r"(https?://[^\s\"'<>]+)", stripped, re.IGNORECASE)
    if url_match:
        stripped = url_match.group(1).strip("\"'<>[](),;")
        # Normalize scheme casing (e.g. Https:// -> https://)
        if stripped[:8].lower() == "https://":
            stripped = "https://" + stripped[8:]
        elif stripped[:7].lower() == "http://":
            stripped = "http://" + stripped[7:]
    else:
        # Reject lines with internal spaces or invalid schemes like ftp:/
        if " " in stripped or ":/" in stripped:
            return None
        # Default to https:// if protocol is omitted
        stripped = f"https://{stripped}"

    try:
        parsed = urlparse(stripped)
        # A valid URL must have at least a scheme and a valid domain netloc with a dot
        if parsed.scheme in ("http", "https") and parsed.netloc and "." in parsed.netloc:
            # Strip trailing slash so 'site.com/path/' and 'site.com/path' normalize to the same URL
            normalized = stripped.rstrip("/")
            return normalized
        return None
    except Exception as exc:
        logger.warning(f"Failed to parse URL '{raw_url}': {exc}")
        return None


def process_url_input(raw_input: str) -> List[str]:
    """
    Processes multiline or comma/space-separated raw text into a deduplicated list of valid URLs.
    
    Args:
        raw_input: Multiline text entered by the user containing URLs.
        
    Returns:
        List[str]: Cleaned, validated, and deduplicated URLs in original order.
    """
    if not raw_input:
        return []

    lines = raw_input.splitlines()
    unique_urls: List[str] = []
    seen = set()

    for line in lines:
        # Also allow comma-separated URLs on a single line
        parts = [p for p in re.split(r"[,;]+", line) if p.strip()]
        for part in parts:
            cleaned = clean_url(part)
            if cleaned and cleaned not in seen:
                seen.add(cleaned)
                unique_urls.append(cleaned)

    logger.info(f"Processed {len(lines)} raw input lines into {len(unique_urls)} valid unique URLs.")
    if not unique_urls:
        logger.warning(f"No valid URLs extracted from raw input: {repr(raw_input[:200])}")
    return unique_urls


def explain_invalid_urls(raw_input: str) -> str:
    """Returns a helpful diagnostic message explaining why the input had no valid URLs."""
    lines = [ln.strip() for ln in (raw_input or "").splitlines() if ln.strip()]
    if not lines:
        return "Input is empty. Please enter at least one valid URL (e.g. https://luma.com/sf)."

    reasons = []
    for ln in lines[:3]:
        cleaned = _ZERO_WIDTH_RE.sub("", ln).strip().strip("\"'<>[](),;")
        test_url = cleaned if re.match(r"^https?://", cleaned, re.IGNORECASE) else f"https://{cleaned}"
        try:
            parsed = urlparse(test_url)
            if parsed.netloc and "." not in parsed.netloc:
                suggestion = f"https://{parsed.netloc}.com{parsed.path}"
                reasons.append(
                    f"'{ln}' is missing a domain extension like '.com' (did you mean '{suggestion}'?)"
                )
            else:
                reasons.append(f"'{ln}' is not a valid http/https URL")
        except Exception:
            reasons.append(f"'{ln}' could not be parsed as a URL")

    return "No valid URLs were found. " + "; ".join(reasons)

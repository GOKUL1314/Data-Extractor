# core/synonyms.py - Centralized dictionary mapping user instruction terms to canonical columns.
# This file provides a single, easy-to-edit mapping of synonyms and variants to standard column names.

from typing import Dict, List, Optional, Tuple

# Canonical column definitions and their recognized keyword variants / synonyms.
# Each entry maps: Canonical Name -> list of lower-case synonym phrases.
SYNONYMS_MAP: Dict[str, List[str]] = {
    "Name": [
        "title",
        "name",
        "event name",
        "role",
        "job title",
        "headline",
        "job",
        "article title",
        "event",
        "position",
        "item",
        "product",
        "course name",
        "listing",
        "article",
        "story",
        "topic",
    ],
    "Date": [
        "date",
        "day",
        "when",
        "last day to apply",
        "deadline",
        "event date",
        "published date",
        "posting date",
        "date posted",
        "application deadline",
        "time posted",
    ],
    "Time": [
        "time",
        "start time",
        "event time",
        "hours",
        "schedule",
        "timing",
    ],
    "Host": [
        "host",
        "organizer",
        "company",
        "author",
        "by",
        "speaker",
        "creator",
        "publisher",
        "hiring company",
        "employer",
        "source",
    ],
    "Location": [
        "location",
        "venue",
        "place",
        "city",
        "address",
        "where",
        "event location",
        "job location",
    ],
    "Link": [
        "link",
        "url",
        "registration link",
        "apply link",
        "article link",
        "source link",
        "event link",
        "details link",
        "href",
        "page link",
    ],
    "Skills": [
        "skills",
        "requirements",
        "required skills",
        "qualifications",
        "tech stack",
        "technologies",
    ],
    "Description": [
        "description",
        "summary",
        "details",
        "about",
        "bio",
        "overview",
        "snippet",
    ],
    "Price": [
        "price",
        "salary",
        "cost",
        "fee",
        "compensation",
        "ticket price",
        "pay",
    ],
    "Points": [
        "points",
        "score",
        "upvotes",
        "votes",
        "karma",
    ],
    "Comments": [
        "comments",
        "comment count",
        "replies",
        "discuss",
        "number of comments",
    ],
    "Category": [
        "category",
        "type",
        "tag",
        "tags",
        "genre",
    ],
}

# Standard data types for canonical columns
COLUMN_DATA_TYPES: Dict[str, str] = {
    "Name": "string",
    "Date": "date",
    "Time": "time",
    "Host": "string",
    "Location": "string",
    "Link": "url",
    "Skills": "string",
    "Description": "string",
    "Price": "string",
    "Points": "number",
    "Comments": "number",
    "Category": "string",
    "Source Website": "url",
}


def match_synonym(phrase: str) -> Optional[str]:
    """
    Matches a normalized user phrase to a canonical column name.
    
    Args:
        phrase: Normalized phrase string from user prompt.
        
    Returns:
        Optional[str]: Canonical column name if matched, else None.
    """
    import re

    cleaned = phrase.strip().lower()
    if not cleaned:
        return None

    # Exact match first
    for canonical, synonyms in SYNONYMS_MAP.items():
        if cleaned == canonical.lower() or cleaned in synonyms:
            return canonical

    # Word boundary match for synonym phrases
    for canonical, synonyms in SYNONYMS_MAP.items():
        for syn in synonyms:
            if re.search(rf"\b{re.escape(syn)}\b", cleaned):
                return canonical

    return None

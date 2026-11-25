# core/classifier.py - Step 2: Rule-based website category classification.
# Decides site type (events, jobs, news, education, ecommerce, other) deterministically
# using JSON-LD @type tags, URL indicators, page title, and keyword frequencies.

import json
import re
from typing import Dict, Optional, Tuple
from bs4 import BeautifulSoup
from models.schemas import SiteInfo
from utils.logger import logger

# URL indicator patterns
URL_PATTERNS = {
    "events": [r"lu\.ma", r"luma\.com", r"eventbrite", r"meetup\.com", r"/events?", r"/calendar", r"/summit", r"/hackathon"],
    "jobs": [r"/jobs?", r"/careers?", r"/positions?", r"fake-jobs", r"greenhouse\.io", r"lever\.co", r"workable\.com", r"indeed\.com"],
    "news": [r"news\.ycombinator\.com", r"/news", r"/blog", r"/articles?", r"techcrunch\.com", r"/stories"],
    "education": [r"/courses?", r"/tutorials?", r"/learn", r"/class(?:es)?", r"coursera\.org", r"udemy\.com", r"edx\.org"],
    "ecommerce": [r"/shop", r"/products?", r"/store", r"/cart", r"shopify\.com", r"/catalog"],
}

# Title and content keyword sets
CATEGORY_KEYWORDS = {
    "events": ["event", "events", "calendar", "hackathon", "meetup", "summit", "conference", "tickets", "rsvp"],
    "jobs": ["job", "jobs", "career", "careers", "hiring", "position", "positions", "salary", "apply now"],
    "news": ["news", "articles", "headline", "headlines", "breaking", "points", "comments", "author", "editor"],
    "education": ["course", "courses", "tutorial", "tutorials", "lesson", "lessons", "learn", "curriculum", "syllabus"],
    "ecommerce": ["price", "cart", "add to cart", "checkout", "buy", "discount", "sku", "in stock", "store"],
}


def _check_json_ld(soup: BeautifulSoup) -> Optional[Tuple[str, str]]:
    """Checks JSON-LD scripts for standard schema.org @type definitions."""
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        content = (script.string or "").strip()
        if not content:
            continue
        try:
            data = json.loads(content)
            items = data if isinstance(data, list) else [data]
            for item in items:
                if not isinstance(item, dict):
                    continue
                type_val = item.get("@type", "")
                types = type_val if isinstance(type_val, list) else [type_val]

                # Check nested ItemList elements
                if "ItemList" in types and "itemListElement" in item:
                    elements = item["itemListElement"]
                    if elements and isinstance(elements, list):
                        first = elements[0]
                        if isinstance(first, dict) and "item" in first and isinstance(first["item"], dict):
                            sub_type = first["item"].get("@type", "")
                            types.append(sub_type)

                for t in types:
                    t_str = str(t)
                    if "Event" in t_str:
                        return "events", f"Rule: JSON-LD @type contains '{t_str}'"
                    if "JobPosting" in t_str:
                        return "jobs", f"Rule: JSON-LD @type contains '{t_str}'"
                    if any(n in t_str for n in ("NewsArticle", "Article", "BlogPosting")):
                        return "news", f"Rule: JSON-LD @type contains '{t_str}'"
                    if any(p in t_str for p in ("Product", "Offer", "IndividualProduct")):
                        return "ecommerce", f"Rule: JSON-LD @type contains '{t_str}'"
                    if any(e in t_str for e in ("Course", "EducationalOccupationalCredential")):
                        return "education", f"Rule: JSON-LD @type contains '{t_str}'"
        except Exception:
            continue
    return None


def _check_url(url: str) -> Optional[Tuple[str, str]]:
    """Checks URL domain and path tokens against category patterns."""
    url_lower = url.lower()
    for cat, patterns in URL_PATTERNS.items():
        for pat in patterns:
            if re.search(pat, url_lower):
                return cat, f"Rule: URL matched pattern '{pat}'"
    return None


def _check_title_and_keywords(soup: BeautifulSoup, raw_text: str) -> Tuple[str, str]:
    """Inspects page title and keyword counts to categorize the page."""
    title_text = ""
    if soup.title and soup.title.string:
        title_text = soup.title.string.strip().lower()

    # Check title first
    if title_text:
        for cat, keywords in CATEGORY_KEYWORDS.items():
            for kw in keywords:
                if re.search(rf"\b{re.escape(kw)}\b", title_text):
                    return cat, f"Rule: Page title matched '{kw}'"

    # Count keyword frequencies across body text
    text_lower = (raw_text or "").lower()
    scores: Dict[str, int] = {cat: 0 for cat in CATEGORY_KEYWORDS}
    for cat, keywords in CATEGORY_KEYWORDS.items():
        for kw in keywords:
            matches = len(re.findall(rf"\b{re.escape(kw)}\b", text_lower))
            scores[cat] += matches

    best_cat = max(scores, key=scores.get)
    if scores[best_cat] >= 2:
        return best_cat, f"Rule: Text keyword frequency matched '{best_cat}' ({scores[best_cat]} occurrences)"

    return "other", "Rule: No specific category rule matched; classified as 'other'"


def classify_site(
    url: str,
    raw_text_or_html: str,
    client: Optional[object] = None,
) -> SiteInfo:
    """
    Classifies a website into a category using deterministic rule inspection.
    
    Args:
        url: The website URL.
        raw_text_or_html: Raw HTML or cleaned text.
        client: Ignored (kept for backwards compatibility).
        
    Returns:
        SiteInfo: Classified site information including the rule that matched.
    """
    soup = BeautifulSoup(raw_text_or_html or "", "lxml")

    # 1. JSON-LD @type rule
    json_ld_match = _check_json_ld(soup)
    if json_ld_match:
        site_type, reason = json_ld_match
        logger.info(f"Classified '{url}' as '{site_type}'. {reason}")
        return SiteInfo(url=url, site_type=site_type, reason=reason)

    # 2. URL word patterns rule
    url_match = _check_url(url)
    if url_match:
        site_type, reason = url_match
        logger.info(f"Classified '{url}' as '{site_type}'. {reason}")
        return SiteInfo(url=url, site_type=site_type, reason=reason)

    # 3. Title & keyword frequency rules
    site_type, reason = _check_title_and_keywords(soup, raw_text_or_html)
    logger.info(f"Classified '{url}' as '{site_type}'. {reason}")
    return SiteInfo(url=url, site_type=site_type, reason=reason)

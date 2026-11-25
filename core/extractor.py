# core/extractor.py - Step 6: Multi-strategy rule-based data extraction engine.
# Executes 6 deterministic extraction strategies in sequence:
#   a) JSON-LD (<script type="application/ld+json">)
#   b) Embedded JSON (__NEXT_DATA__, __INITIAL_STATE__)
#   c) Repeated DOM Cards (with field_detectors)
#   d) Heading Sections (date/category headings above cards)
#   e) Label Rules ("Label: Value" lines and list sections)
#   f) HTML Tables (table rows and columns)

import json
import re
from typing import Any, Callable, Dict, List, Optional, Sequence, Set, Tuple
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse
from bs4 import BeautifulSoup, Tag
from core.field_detectors import (
    detect_comments,
    detect_date,
    detect_host,
    detect_location,
    detect_points,
    detect_price,
    detect_time,
    extract_fields_from_dom_node,
)
from models.schemas import ExtractionPlan, Row
from utils.logger import logger


def _clean_str(val: Any) -> str:
    """Cleans a string or extracts readable text."""
    if val is None:
        return ""
    text = str(val).strip()
    return re.sub(r"\s+", " ", text)


def _strip_query_param(url: str, key: str, value: Optional[str] = None) -> str:
    """Removes a specific query parameter (e.g. 'k=c') from a URL."""
    parsed = urlparse(url)
    if not parsed.query:
        return url
    filtered = [
        (k, v)
        for k, v in parse_qsl(parsed.query, keep_blank_values=True)
        if not (k == key and (value is None or v == value))
    ]
    return urlunparse(parsed._replace(query=urlencode(filtered)))


def _is_calendar_anchor(tag: Tag) -> bool:
    """Returns True if an anchor tag is a Luma calendar card link (contains '?k=c' or k=c param)."""
    href = (tag.get("href") or "").strip()
    if not href:
        return False
    if "?k=c" in href or "&k=c" in href:
        return True
    parsed = urlparse(href)
    return any(k == "k" and v == "c" for k, v in parse_qsl(parsed.query))


def _is_inside_calendar_section(tag: Tag) -> bool:
    """Returns True if the element is or sits inside a dedicated calendars container."""
    for el in [tag, *tag.parents]:
        if not isinstance(el, Tag):
            continue
        cls_str = " ".join(el.get("class") or []).lower()
        if any(k in cls_str for k in ("calendars-section", "calendar-list", "calendar-item")):
            return True
    return False


def _format_iso_datetime(iso_str: str, tz_name: Optional[str] = None) -> Tuple[Optional[str], Optional[str]]:
    """Converts an ISO 8601 datetime string to (DD-MM-YYYY, HH:MM)."""
    if not iso_str or not isinstance(iso_str, str):
        return None, None
    try:
        from datetime import datetime
        import zoneinfo

        # Normalize Zulu indicator
        clean_iso = iso_str.replace("Z", "+00:00")
        dt = datetime.fromisoformat(clean_iso)
        if tz_name:
            try:
                dt = dt.astimezone(zoneinfo.ZoneInfo(tz_name))
            except Exception:
                pass
        date_str = dt.strftime("%d-%m-%Y")
        time_str = dt.strftime("%H:%M")
        return date_str, time_str
    except Exception:
        # Fallback regex extraction
        date_match = re.search(r"(\d{4})-(\d{2})-(\d{2})", iso_str)
        time_match = re.search(r"T(\d{2}:\d{2})", iso_str)
        d_str = f"{date_match.group(3)}-{date_match.group(2)}-{date_match.group(1)}" if date_match else None
        t_str = time_match.group(1) if time_match else None
        return d_str, t_str


def _find_luma_sublocalities(soup: BeautifulSoup) -> Dict[str, str]:
    """Finds specific sublocalities (e.g. SoMa, South Beach) from __NEXT_DATA__ if present."""
    sublocalities: Dict[str, str] = {}
    next_script = soup.find("script", id="__NEXT_DATA__")
    if next_script and next_script.string:
        try:
            data = json.loads(next_script.string)
            events = data.get("props", {}).get("pageProps", {}).get("initialData", {}).get("data", {}).get("events", [])
            for ev in events:
                item = ev.get("event", {})
                url_slug = item.get("url", "")
                geo = item.get("geo_address_info", {})
                sublocality = geo.get("sublocality") or geo.get("city")
                if url_slug and sublocality:
                    sublocalities[url_slug] = sublocality
        except Exception:
            pass
    return sublocalities


# ---------------------------------------------------------------------------
# Strategy a: JSON-LD Extraction
# ---------------------------------------------------------------------------

def _extract_json_ld(soup: BeautifulSoup, base_url: str) -> List[Dict[str, Any]]:
    """Extracts records from application/ld+json scripts."""
    records: List[Dict[str, Any]] = []
    sublocalities = _find_luma_sublocalities(soup)

    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        content = (script.string or "").strip()
        if not content:
            continue
        try:
            data = json.loads(content)
            items = data if isinstance(data, list) else [data]
            for root_item in items:
                if not isinstance(root_item, dict):
                    continue

                candidates: List[Dict[str, Any]] = []
                # Check for ItemList
                if root_item.get("@type") == "ItemList" and "itemListElement" in root_item:
                    for el in root_item["itemListElement"]:
                        if isinstance(el, dict):
                            sub = el.get("item") if isinstance(el.get("item"), dict) else el
                            candidates.append(sub)
                elif "@graph" in root_item and isinstance(root_item["@graph"], list):
                    candidates.extend([g for g in root_item["@graph"] if isinstance(g, dict)])
                else:
                    candidates.append(root_item)

                for item in candidates:
                    t_val = str(item.get("@type", ""))
                    if not any(k in t_val for k in ("Event", "JobPosting", "Article", "NewsArticle", "Product", "Course")):
                        continue

                    rec: Dict[str, Any] = {}
                    # Name
                    rec["Name"] = _clean_str(item.get("name") or item.get("headline") or item.get("title"))

                    # Link
                    raw_link = item.get("url") or item.get("@id") or ""
                    if raw_link:
                        rec["Link"] = urljoin(base_url, raw_link)

                    # Date and Time
                    start_date = item.get("startDate") or item.get("datePublished") or item.get("datePosted")
                    if start_date:
                        d_str, t_str = _format_iso_datetime(start_date)
                        if d_str:
                            rec["Date"] = d_str
                        if t_str:
                            rec["Time"] = t_str

                    # Host / Organizer
                    org = item.get("organizer") or item.get("hiringOrganization") or item.get("author") or item.get("publisher")
                    if isinstance(org, list) and org:
                        org = org[0]
                    if isinstance(org, dict):
                        rec["Host"] = _clean_str(org.get("name"))
                    elif isinstance(org, str):
                        rec["Host"] = _clean_str(org)

                    # Location (with sublocality enrichment if available)
                    loc = item.get("location")
                    url_slug = raw_link.rstrip("/").split("/")[-1] if raw_link else ""
                    if url_slug in sublocalities:
                        rec["Location"] = sublocalities[url_slug]
                    elif isinstance(loc, dict):
                        rec["Location"] = _clean_str(loc.get("name") or loc.get("address", {}).get("addressLocality"))
                    elif isinstance(loc, str):
                        rec["Location"] = _clean_str(loc)

                    # Description
                    if item.get("description"):
                        rec["Description"] = _clean_str(item.get("description"))

                    # Price
                    offers = item.get("offers")
                    if isinstance(offers, list) and offers:
                        offers = offers[0]
                    if isinstance(offers, dict) and "price" in offers:
                        price_val = str(offers["price"])
                        curr = offers.get("priceCurrency", "")
                        rec["Price"] = f"{curr} {price_val}".strip() if curr else price_val

                    if rec.get("Name") or rec.get("Link"):
                        records.append(rec)
        except Exception:
            continue

    return records


# ---------------------------------------------------------------------------
# Strategy b: Embedded JSON Extraction (__NEXT_DATA__ and similar)
# ---------------------------------------------------------------------------

def _extract_embedded_json(soup: BeautifulSoup, base_url: str) -> List[Dict[str, Any]]:
    """Extracts records from __NEXT_DATA__ or script objects containing structured lists."""
    records: List[Dict[str, Any]] = []
    next_script = soup.find("script", id="__NEXT_DATA__")
    if not next_script or not next_script.string:
        return records

    try:
        data = json.loads(next_script.string)
        # 1. Specifically check Luma events structure
        events = data.get("props", {}).get("pageProps", {}).get("initialData", {}).get("data", {}).get("events", [])
        for ev in events:
            item = ev.get("event", {})
            cal = ev.get("calendar", {})
            name = _clean_str(item.get("name"))
            if not name:
                continue

            rec: Dict[str, Any] = {"Name": name}
            slug = item.get("url") or item.get("api_id")
            if slug:
                rec["Link"] = urljoin(base_url, slug)

            # Date and Time with timezone support
            start_at = item.get("start_at")
            tz = item.get("timezone", "America/Los_Angeles")
            if start_at:
                d_str, t_str = _format_iso_datetime(start_at, tz_name=tz)
                if d_str:
                    rec["Date"] = d_str
                if t_str:
                    rec["Time"] = t_str

            # Host from calendar or hosts list
            if cal.get("name"):
                rec["Host"] = _clean_str(cal.get("name"))
            elif ev.get("hosts") and isinstance(ev["hosts"], list):
                rec["Host"] = _clean_str(ev["hosts"][0].get("name"))

            # Location from sublocality or city_state
            geo = item.get("geo_address_info", {})
            rec["Location"] = _clean_str(geo.get("sublocality") or geo.get("city_state") or geo.get("city"))

            records.append(rec)

        if records:
            return records

        # 2. Generic scan for arrays of objects with title and url keys
        collected_arrays: List[List[Dict[str, Any]]] = []

        def find_candidate_arrays(node: Any, depth: int = 0):
            if depth > 7:
                return
            if isinstance(node, list):
                if len(node) >= 2 and all(isinstance(x, dict) for x in node[:5]):
                    first = node[0]
                    has_title = any(k in first for k in ("name", "title", "headline", "job_title"))
                    has_url = any(k in first for k in ("url", "link", "href", "slug", "path"))
                    if has_title and has_url:
                        collected_arrays.append(node)
                for item in node:
                    find_candidate_arrays(item, depth + 1)
            elif isinstance(node, dict):
                for v in node.values():
                    find_candidate_arrays(v, depth + 1)

        find_candidate_arrays(data)
        for arr in collected_arrays:
            for item in arr:
                rec = {}
                name = item.get("title") or item.get("name") or item.get("headline")
                if not name or not isinstance(name, str):
                    continue
                rec["Name"] = _clean_str(name)
                link_val = item.get("url") or item.get("link") or item.get("href") or item.get("slug")
                if link_val:
                    rec["Link"] = urljoin(base_url, str(link_val))
                if item.get("date") or item.get("created_at"):
                    rec["Date"] = _clean_str(item.get("date") or item.get("created_at"))
                records.append(rec)
            if records:
                break

    except Exception:
        pass

    return records


# ---------------------------------------------------------------------------
# Strategy c & d: Repeated Cards and Heading Sections
# ---------------------------------------------------------------------------

def _extract_hacker_news_rows(soup: BeautifulSoup, base_url: str) -> List[Dict[str, Any]]:
    """Specialized detector for Hacker News (news.ycombinator.com) post structure."""
    records: List[Dict[str, Any]] = []
    athings = soup.find_all("tr", class_="athing")
    for athing in athings:
        titleline = athing.find(class_="titleline")
        if not titleline:
            continue
        link_tag = titleline.find("a", href=True)
        if not link_tag:
            continue

        title = link_tag.get_text(strip=True)
        link = urljoin(base_url, link_tag["href"])
        rec: Dict[str, Any] = {"Name": title, "Link": link}

        # Subtext row is immediate next sibling tr containing class="subtext" or class="subline"
        subtext = athing.find_next_sibling("tr")
        if subtext:
            subline = subtext.find(class_="subtext") or subtext.find(class_="subline") or subtext
            score_tag = subline.find(class_="score")
            if score_tag:
                rec["Points"] = detect_points(score_tag.get_text()) or score_tag.get_text(strip=True)

            user_tag = subline.find(class_="hnuser")
            if user_tag:
                rec["Host"] = user_tag.get_text(strip=True)

            # Comments are in the subtext link with comments/discuss
            links = subline.find_all("a", href=True)
            for lk in links:
                txt = lk.get_text(strip=True).replace("\xa0", " ")
                if "comment" in txt or "discuss" in txt:
                    rec["Comments"] = detect_comments(txt) or ("0" if "discuss" in txt else txt)

        records.append(rec)
    return records


def _extract_repeated_cards(soup: BeautifulSoup, base_url: str) -> List[Dict[str, Any]]:
    """Extracts records by detecting repeated card groups or timeline sections."""
    records: List[Dict[str, Any]] = []

    # 1. Check for Hacker News
    hn_records = _extract_hacker_news_rows(soup, base_url)
    if hn_records:
        return hn_records

    # 2. Check for Heading Sections (e.g., Luma .timeline-section with date headings)
    timeline_sections = soup.find_all(class_=lambda c: c and "timeline-section" in str(c).lower())
    if timeline_sections:
        for section in timeline_sections:
            date_label = None
            date_title_tag = section.find(class_=lambda c: c and any(k in str(c).lower() for k in ("date-title", "timeline-title")))
            if date_title_tag:
                date_label = " ".join(date_title_tag.stripped_strings)

            cards = section.find_all(class_=lambda c: c and any(k in str(c).lower() for k in ("card-wrapper", "content-card", "event-card")))
            if not cards:
                cards = [
                    a for a in section.find_all("a", href=True)
                    if a.get("aria-label") and not _is_calendar_anchor(a)
                ]

            for card in cards:
                rec = extract_fields_from_dom_node(card, base_url, inherited_date=date_label)
                if rec.get("Link") and "k=c" in rec["Link"]:
                    continue
                if rec.get("Name") or rec.get("Link"):
                    records.append(rec)

        if records:
            return records

    # 3. Repeated card container detection by CSS class frequency
    class_groups: Dict[str, List[Tag]] = {}
    for el in soup.find_all(["div", "article", "section", "li"]):
        classes = el.get("class")
        if not classes or _is_inside_calendar_section(el):
            continue
        # Join classes into a normalized selector
        cls_key = f"{el.name}." + ".".join(classes)
        # Must contain at least one non-calendar link
        anchors = el.find_all("a", href=True)
        if any(not _is_calendar_anchor(a) for a in anchors):
            class_groups.setdefault(cls_key, []).append(el)

    # Find the largest repeated group of cards
    valid_groups = [grp for grp in class_groups.values() if len(grp) >= 2]
    if valid_groups:
        # Choose the group with the most items and reasonable card length
        best_group = max(valid_groups, key=lambda g: len(g))
        # Determine if preceding heading exists
        for node in best_group:
            # Look for heading before this card
            inherited_date = None
            prev = node.find_previous(["h1", "h2", "h3", "h4"])
            if prev:
                prev_text = prev.get_text(strip=True)
                if detect_date(prev_text):
                    inherited_date = prev_text

            rec = extract_fields_from_dom_node(node, base_url, inherited_date=inherited_date)
            if rec.get("Link") and "k=c" in rec["Link"]:
                continue
            if rec.get("Name") or rec.get("Link"):
                records.append(rec)

    return records


# ---------------------------------------------------------------------------
# Section-Targeted Extraction (Generic Heading -> Container -> Cards & Calendars)
# ---------------------------------------------------------------------------

def _find_section_container(
    soup: BeautifulSoup,
    keywords: Sequence[str],
    card_predicate: Optional[Callable[[Tag], bool]] = None,
    max_ancestors: int = 4,
) -> Tuple[Optional[Tag], Optional[Tag]]:
    """
    Finds the heading matching any keyword and returns (heading_tag, section_container).
    Walks up to max_ancestors parents (stopping before body/html) to locate the tightest
    container holding the section's cards.
    """
    lowered_keywords = [k.lower() for k in keywords if k]
    if not lowered_keywords:
        return None, None

    heading_candidates = soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6"])
    if not heading_candidates:
        heading_candidates = soup.find_all(
            attrs={"role": "heading"}
        ) or soup.find_all(
            class_=lambda c: c and any(k in str(c).lower() for k in ("section-title", "heading", "title"))
        )

    matched_heading: Optional[Tag] = None
    for kw in lowered_keywords:
        for h in heading_candidates:
            txt = _clean_str(h.get_text(" ", strip=True)).lower()
            if kw in txt:
                matched_heading = h
                break
        if matched_heading is not None:
            break

    if matched_heading is None:
        return None, None

    ancestors: List[Tag] = []
    curr = matched_heading.parent
    for _ in range(max_ancestors):
        if not isinstance(curr, Tag) or curr.name in ("body", "html", "[document]"):
            break
        ancestors.append(curr)
        curr = curr.parent

    if card_predicate is not None:
        for min_count in (2, 1):
            for anc in ancestors:
                matched_links = [a for a in anc.find_all("a", href=True) if card_predicate(a)]
                if len(matched_links) >= min_count:
                    return matched_heading, anc

    for min_count in (2, 1):
        for anc in ancestors:
            if len(anc.find_all("a", href=True)) >= min_count:
                return matched_heading, anc

    return matched_heading, (ancestors[0] if ancestors else matched_heading.parent)


def _extract_card_name_and_description(card: Tag) -> Tuple[str, str]:
    """Builds (Name, Description) from a card's meaningful text lines, excluding 'Follow'."""
    lines: List[str] = []
    for chunk in card.stripped_strings:
        for subline in chunk.splitlines():
            cleaned = _clean_str(subline)
            if not cleaned or cleaned == "\u200b":
                continue
            if cleaned.lower() == "follow":
                continue
            lines.append(cleaned)

    if not lines:
        return "", ""
    name = lines[0]
    description = _clean_str(" ".join(lines[1:])) if len(lines) > 1 else ""
    return name, description


def _extract_section_cards(
    soup: BeautifulSoup,
    base_url: str,
    heading_keywords: Sequence[str],
    link_predicate: Optional[Callable[[Tag], bool]] = None,
    strip_query_key: Optional[str] = None,
    strip_query_val: Optional[str] = None,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    Generic section-targeted extractor: locates heading by keyword, scopes to its
    section container, and extracts repeated card records inside that container.
    """
    heading_tag, container = _find_section_container(
        soup, heading_keywords, card_predicate=link_predicate
    )
    heading_text = _clean_str(heading_tag.get_text(" ", strip=True)) if heading_tag else None

    if container is not None:
        all_anchors = container.find_all("a", href=True)
        candidate_anchors = (
            [a for a in all_anchors if link_predicate(a)]
            if link_predicate is not None
            else all_anchors
        )
    else:
        all_anchors = soup.find_all("a", href=True)
        candidate_anchors = (
            [a for a in all_anchors if link_predicate(a)]
            if link_predicate is not None
            else []
        )

    section_diag: Dict[str, Any] = {
        "section_heading_found": heading_tag is not None,
        "section_heading_text": heading_text,
        "candidate_anchors_seen": len(candidate_anchors),
    }

    if container is None:
        return [], section_diag

    records: List[Dict[str, Any]] = []
    if link_predicate is not None:
        for anchor in candidate_anchors:
            name, description = _extract_card_name_and_description(anchor)
            abs_link = urljoin(base_url, anchor["href"].strip())
            if strip_query_key:
                abs_link = _strip_query_param(abs_link, strip_query_key, strip_query_val)
            rec: Dict[str, Any] = {}
            if name:
                rec["Name"] = name
            if description:
                rec["Description"] = description
            if abs_link:
                rec["Link"] = abs_link
            if rec.get("Name") or rec.get("Link"):
                records.append(rec)
        return records, section_diag

    # Generic repeated-card mode within the scoped section container
    class_groups: Dict[str, List[Tag]] = {}
    for el in container.find_all(["div", "article", "li", "a"]):
        if el.name == "a" and not el.get("href"):
            continue
        classes = el.get("class")
        cls_key = f"{el.name}." + ".".join(classes) if classes else el.name
        if el.name == "a" or el.find("a", href=True):
            class_groups.setdefault(cls_key, []).append(el)

    valid_groups = [grp for grp in class_groups.values() if len(grp) >= 2]
    cards = max(valid_groups, key=len) if valid_groups else candidate_anchors
    for card in cards:
        if card.name == "a":
            name, description = _extract_card_name_and_description(card)
            rec = {"Link": urljoin(base_url, card["href"].strip())}
            if name:
                rec["Name"] = name
            if description:
                rec["Description"] = description
        else:
            rec = extract_fields_from_dom_node(card, base_url)
        if rec.get("Name") or rec.get("Link"):
            records.append(rec)

    return records, section_diag


def _extract_calendar_cards(
    soup: BeautifulSoup,
    base_url: str,
    diagnostics: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """
    Extracts calendar cards from a Calendars heading section (e.g., 'Popular Calendars').
    Collects anchors whose href contains '?k=c', builds Name (excluding 'Follow'),
    Description, and absolute Link with '?k=c' stripped.
    """
    records, section_diag = _extract_section_cards(
        soup=soup,
        base_url=base_url,
        heading_keywords=("calendars", "calendar"),
        link_predicate=_is_calendar_anchor,
        strip_query_key="k",
        strip_query_val="c",
    )
    if diagnostics is not None:
        diagnostics.update(section_diag)
    return records


# ---------------------------------------------------------------------------
# Strategy e: Label Rule Extraction ("Label: Value" and List Sections)
# ---------------------------------------------------------------------------

def _extract_label_rules(soup: BeautifulSoup, base_url: str) -> List[Dict[str, Any]]:
    """Extracts records using 'Label: value' lines and definition lists."""
    records: List[Dict[str, Any]] = []
    # Search for blocks containing multiple 'Label: value' patterns
    for container in soup.find_all(["div", "section", "article"]):
        text = container.get_text()
        pairs = re.findall(r"([A-Za-z\s]{3,20}):\s*([^\n\r]+)", text)
        if len(pairs) >= 3:
            rec: Dict[str, Any] = {}
            for label, val in pairs:
                rec[label.strip()] = val.strip()
            first_link = container.find("a", href=True)
            if first_link:
                rec["Link"] = urljoin(base_url, first_link["href"])
            records.append(rec)
            break
    return records


# ---------------------------------------------------------------------------
# Strategy f: HTML Table Extraction
# ---------------------------------------------------------------------------

def _extract_tables(soup: BeautifulSoup, base_url: str) -> List[Dict[str, Any]]:
    """Extracts records from <table> elements where rows become records."""
    records: List[Dict[str, Any]] = []
    tables = soup.find_all("table")
    for table in tables:
        rows = table.find_all("tr")
        if len(rows) < 2:
            continue

        # Extract headers from first row
        headers: List[str] = []
        first_row_cells = rows[0].find_all(["th", "td"])
        for cell in first_row_cells:
            headers.append(cell.get_text(strip=True) or f"Col_{len(headers)+1}")

        # Extract subsequent rows
        for r in rows[1:]:
            cells = r.find_all("td")
            if not cells:
                continue
            rec: Dict[str, Any] = {}
            for i, cell in enumerate(cells):
                col_name = headers[i] if i < len(headers) else f"Col_{i+1}"
                link = cell.find("a", href=True)
                if link and "Link" not in rec:
                    rec["Link"] = urljoin(base_url, link["href"])

                if col_name.lower() == "link" and link:
                    rec["Link"] = urljoin(base_url, link["href"])
                else:
                    rec[col_name] = cell.get_text(strip=True)

            if any(rec.values()):
                records.append(rec)

        if records:
            break

    return records


# ---------------------------------------------------------------------------
# Main Orchestrator: Multi-Strategy Execution & Mapping
# ---------------------------------------------------------------------------

def _is_login_or_block_page(html: str) -> Tuple[bool, str]:
    """Detects if page content indicates a CAPTCHA, bot block, or login wall."""
    lower = html.lower()
    if any(k in lower for k in ("challenge-running", "cf-browser-verification", "turnstile", "captcha", "datadome", "perimeterx")):
        return True, "Cloudflare / Bot Challenge Page"
    if any(k in lower for k in ("access denied", "403 forbidden", "just a moment...")):
        return True, "Access Denied / 403 Forbidden"
    if "<input type=\"password\"" in lower or ("sign in" in lower and "log in" in lower and len(lower) < 2000):
        return True, "Authentication / Login Wall"
    return False, ""


def extract_rows_from_text(
    html_content: str,
    source_url: str,
    plan: ExtractionPlan,
    client: Optional[object] = None,
    manual_selectors: Optional[Dict[str, str]] = None,
) -> Tuple[List[Row], str, Dict[str, Any]]:
    """
    Extracts structured rows matching the plan by trying extraction strategies in order.
    
    Strategies tried in sequence:
      1. JSON-LD (<script type="application/ld+json">)
      2. Embedded JSON (__NEXT_DATA__)
      3. Repeated DOM Cards & Heading Sections
      4. Label Rules
      5. HTML Tables
      
    Args:
        html_content: Raw rendered HTML of the web page.
        source_url: The URL being processed.
        plan: Planned schema columns and types.
        client: Ignored (kept for backwards compatibility).
        manual_selectors: Optional dictionary mapping column names to CSS selectors.
        
    Returns:
        Tuple[List[Row], str, Dict[str, Any]]: (Extracted rows, Strategy used, Diagnostics dict).
    """
    soup = BeautifulSoup(html_content or "", "lxml")
    target_section = getattr(plan, "target_section", None)

    raw_records: List[Dict[str, Any]] = []
    strategy_used = "None"
    section_diag: Dict[str, Any] = {}

    if target_section == "calendars":
        strategies_tried = ["Section-Targeted Calendars (_extract_calendar_cards)"]
        raw_records = _extract_calendar_cards(soup, source_url, diagnostics=section_diag)
        if raw_records:
            strategy_used = "Section-Targeted Calendars (_extract_calendar_cards)"
    elif target_section:
        strategies_tried = [f"Section-Targeted Cards ({target_section})"]
        raw_records, section_diag = _extract_section_cards(
            soup, source_url, heading_keywords=(target_section,)
        )
        if raw_records:
            strategy_used = f"Section-Targeted Cards ({target_section})"
    else:
        strategies_tried = [
            "JSON-LD (<script type='application/ld+json'>)",
            "Embedded JSON (__NEXT_DATA__)",
            "Repeated DOM Cards & Heading Sections",
            "Label Rules",
            "HTML Tables",
        ]

        # Strategy 1: JSON-LD
        raw_records = _extract_json_ld(soup, source_url)
        if raw_records:
            strategy_used = "JSON-LD (<script type='application/ld+json'>)"

        # Strategy 2: Embedded JSON (__NEXT_DATA__)
        if not raw_records:
            raw_records = _extract_embedded_json(soup, source_url)
            if raw_records:
                strategy_used = "Embedded JSON (__NEXT_DATA__)"

        # Strategy 3 & 4: Repeated Cards & Heading Sections
        if not raw_records:
            raw_records = _extract_repeated_cards(soup, source_url)
            if raw_records:
                strategy_used = "Repeated Cards & Heading Sections"

        # Strategy 5: Label Rules
        if not raw_records:
            raw_records = _extract_label_rules(soup, source_url)
            if raw_records:
                strategy_used = "Label Rules"

        # Strategy 6: HTML Tables
        if not raw_records:
            raw_records = _extract_tables(soup, source_url)
            if raw_records:
                strategy_used = "HTML Tables"

    # Diagnostics if no records were found
    is_blocked, block_reason = _is_login_or_block_page(html_content)
    diagnostics: Dict[str, Any] = {
        "text_length": len(soup.get_text().strip()),
        "is_block_or_login": is_blocked,
        "block_reason": block_reason,
        "strategies_tried": strategies_tried,
    }
    if target_section:
        diagnostics["target_section"] = target_section
        diagnostics.update(section_diag)

    if not raw_records:
        logger.warning(f"No records extracted from {source_url}. Diagnostics: {diagnostics}")
        return [], "No matching records found", diagnostics

    # Apply manual CSS selectors if specified by user
    if manual_selectors:
        for col_name, selector in manual_selectors.items():
            if not selector or not selector.strip():
                continue
            matched_nodes = soup.select(selector.strip())
            for idx, raw_rec in enumerate(raw_records):
                if idx < len(matched_nodes):
                    raw_rec[col_name] = matched_nodes[idx].get_text(strip=True)

    # Normalize extracted records against planned columns
    final_rows: List[Row] = []
    seen_links: Set[str] = set()
    duplicate_count = 0

    planned_col_names = [c.name for c in plan.columns]

    for item in raw_records:
        normalized_data: Dict[str, Any] = {}
        for col_name in planned_col_names:
            if col_name == "Source Website":
                normalized_data["Source Website"] = source_url
                continue

            # Look for exact key match or case-insensitive match
            val = item.get(col_name)
            if val is None:
                for k, v in item.items():
                    if k.lower() == col_name.lower():
                        val = v
                        break

            if val is not None and str(val).strip():
                normalized_data[col_name] = str(val).strip()
            else:
                normalized_data[col_name] = "Not found"

        link_val = normalized_data.get("Link", "")
        # Deduplication by Link (drop exact duplicate item URLs)
        if link_val and link_val != "Not found" and link_val in seen_links:
            duplicate_count += 1
            continue
        if link_val and link_val != "Not found":
            seen_links.add(link_val)

        final_rows.append(Row(data=normalized_data, source_url=source_url))

    logger.info(
        f"Extracted {len(final_rows)} rows from {source_url} using strategy: '{strategy_used}' "
        f"({duplicate_count} duplicates removed)."
    )
    diagnostics["duplicate_count"] = duplicate_count
    return final_rows, strategy_used, diagnostics

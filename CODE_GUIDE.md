# 📖 Code Learning Guide: Rule-Based Data Extractor

This guide explains how the rule-based version of the data extraction tool works, tracing the pipeline from raw URLs to categorized spreadsheets.

> **Note:** The previous Gemini API and LLM modules (`llm/`) have been completely removed. All classification, schema planning, and extraction steps are now 100% deterministic, rule-based, and require no API key.

---

## 1. End-to-End Rule-Based Data Flow

```text
User Input:
  - URLs (multiline text)
  - Instruction ("Collect upcoming tech events with date, time, event name...")
  - Optional Manual CSS Selectors (e.g., {"Name": ".job-title"})
       │
       ▼
[Step 1: core/url_handler.py]
  - Strips invisible unicode chars, outer quotes, and normalizes scheme casing
  - Validates domain extensions and deduplicates URLs
  - Output: Clean List[str] of valid URLs (or clear error if domain extension missing)
       │
       ▼
[Step 2: core/instruction_parser.py + core/synonyms.py]
  - Splits instruction by commas, "and", and ignores filler words
  - Maps phrases via core/synonyms.py to canonical columns (Name, Date, Time, Host, Location, Link, etc.)
  - Unmatched phrases become custom columns (handled via label rules)
  - Detects section-targeted instructions (e.g. "calendar(s)" -> `target_section="calendars"`, or `"<noun> section"`)
  - Appends "Source Website" and selects group_by (Date -> Category -> Company/Host -> Location)
  - Output: ExtractionPlan (with optional `target_section`)
       │
       ▼
For each individual URL (Isolated try/except block):
  ┌────────────────────────────────────────────────────────────┐
  │ [Step 3: core/fetcher.py]                                  │
  │   - Fast Path: Attempts quick static GET via httpx         │
  │   - Browser Path: Escalates to headless Playwright         │
  │     Chromium if SPA markers or scroll-heavy site detected  │
  │   - Preserves virtualized timeline sections on scroll      │
  │   - Output: Raw HTML string                                │
  │                                                            │
  │ [Step 4: core/classifier.py]                               │
  │   - Checks JSON-LD @type, URL patterns, Page Title,        │
  │     and keyword frequencies                                │
  │   - Output: SiteInfo (category + matched rule description) │
  │                                                            │
  │ [Step 5: core/extractor.py + core/field_detectors.py]      │
  │   - Parses HTML with BeautifulSoup + lxml                  │
  │   - If plan.target_section is set (e.g., "calendars"):     │
  │       Runs section-targeted extraction first (no fallthru) │
  │   - Otherwise runs 6 strategies in order, stopping at hit: │
  │       a) JSON-LD (<script type="application/ld+json">)     │
  │       b) Embedded JSON (__NEXT_DATA__, etc.)               │
  │       c) Repeated DOM Cards (excludes ?k=c calendar links) │
  │       d) Heading Sections (date headings above cards)      │
  │       e) Label Rules ("Label: value" & lists)              │
  │       f) HTML Tables (<table> headers & rows)              │
  │   - Applies optional manual CSS selectors if provided      │
  │   - Unfound fields become "Not found" (never guessed)      │
  │   - Returns diagnostic details if 0 records found          │
  │     (including section heading & candidate anchor counts)  │
  │   - Output: List[Row], Strategy Name, Diagnostics          │
  └────────────────────────────────────────────────────────────┘
       │
       ▼
[Step 6: core/pipeline.py & core/date_utils.py]
  - Global deduplication by Link
  - Converts ISO dates, "Today", "Tomorrow", "Dec 3" -> DD-MM-YYYY
  - Converts 12-hour times (5:30 PM) -> 24-hour HH:MM (17:30)
  - Strips leading "By " from Host names
       │
       ▼
[Step 7: core/categorizer.py & core/exporter.py]
  - Groups rows chronologically or logically by group_by key
  - Skips exports if 0 rows extracted
  - Otherwise writes CSV, JSON, and multi-tab Excel (.xlsx)
```

---

## 2. Extraction Strategies Explained (`core/extractor.py`)

Strategies are tried in strict priority order, stopping as soon as one returns records:

0. **Section-Targeted Mode (`_extract_calendar_cards` & `_extract_section_cards`)**
   * Activated when `plan.target_section` is detected (e.g., `"calendar(s)"` -> `"calendars"`, or `"<noun> section"`). Runs first and does not fall through to event/page-level strategies.
   * Uses generic section scoping (`_find_section_container`): locates the matching heading, walks up to the tightest container holding the section's cards, and extracts repeated cards.
   * For `"calendars"`, collects Luma calendar anchors (`?k=c`), builds `Name` (first meaningful text line excluding `"Follow"`), `Description` (remaining text), and `Link` (absolute URL with `?k=c` stripped).
1. **Strategy A: JSON-LD (`_extract_json_ld`)**
   * Searches `<script type="application/ld+json">` tags for structured schema.org types (`Event`, `JobPosting`, `Article`, `NewsArticle`, `Product`, `Course`, `ItemList`).
   * Enriches location names with `sublocality` from `__NEXT_DATA__` if available (e.g., yielding `SoMa` or `South Beach` for Luma events).
2. **Strategy B: Embedded JSON (`_extract_embedded_json`)**
   * Inspects `<script id="__NEXT_DATA__">` and recursively scans for arrays of JSON objects containing title-like keys (`name`, `title`, `headline`) and URL keys (`url`, `link`, `slug`).
   * Converts UTC timestamps into local event dates and times using `zoneinfo`.
3. **Strategy C & D: Repeated Cards & Heading Sections (`_extract_repeated_cards`)**
   * Includes specialized handling for Hacker News (`tr.athing` paired with `tr.subtext` for scores and comment counts).
   * Detects timeline/heading sections (like `.timeline-section` on Luma) so cards inherit the date heading sitting above them.
   * Groups repeated sibling containers (`div`, `article`, `section`, `li`) sharing identical tag and CSS classes that contain links, then passes each card to `core/field_detectors.py`.
4. **Strategy E: Label Rules (`_extract_label_rules`)**
   * Extracts key-value pairs from `"Label: Value"` lines (ideal for custom columns and specification blocks).
5. **Strategy F: HTML Tables (`_extract_tables`)**
   * Parses `<table>` elements, mapping `<th>` / first-row headers to column names and subsequent `<tr>` rows to records.

---

## 3. How to Add a New Synonym or Extraction Rule

### Adding a Synonym (`core/synonyms.py`)
Open `core/synonyms.py` and edit `SYNONYMS_MAP`. For example, to map `"venue address"` or `"neighborhood"` to `"Location"`:
```python
    "Location": [
        "location",
        "venue",
        "place",
        "city",
        "venue address",
        "neighborhood",
    ],
```
The `match_synonym()` function uses whole-word boundary matching (`\b...\b`), preventing false substring collisions (like `"tag"` matching `"stages"`).

### Adding a Field Detector (`core/field_detectors.py`)
Add new regex patterns in `core/field_detectors.py` (e.g., `PHONE_PATTERN`) and wire them into `extract_fields_from_dom_node()` to populate new canonical fields automatically on card-based sites.

### Adding a Site Strategy (`core/extractor.py`)
Add a dedicated helper function (e.g. `_extract_custom_layout(soup, base_url)`) and insert it into the strategy cascade inside `extract_rows_from_text()`.

# core/instruction_parser.py - Rule-based instruction parser converting user prompts into column schemas.
# This provides deterministic phrase splitting,
# synonym mapping, filler-word elimination, and rule-based group_by selection.

import re
from typing import List, Optional, Set
from core.synonyms import COLUMN_DATA_TYPES, match_synonym
from models.schemas import ColumnSpec, ExtractionPlan
from utils.logger import logger

# Filler words and command prefixes to ignore when parsing instructions
FILLER_WORDS: Set[str] = {
    "collect",
    "all",
    "with",
    "upcoming",
    "the",
    "extract",
    "get",
    "find",
    "please",
    "top",
    "of",
    "for",
    "a",
    "an",
    "items",
    "records",
    "data",
    "list",
    "from",
    "each",
    "every",
    "containing",
    "fields",
    "columns",
    "info",
    "information",
    "tech",
    "developer",
}


def _clean_phrase(phrase: str) -> str:
    """Removes filler words and punctuation from an extracted phrase."""
    # Replace non-alphanumeric (except hyphens) with spaces
    cleaned = re.sub(r"[^\w\s-]", " ", phrase)
    tokens = cleaned.strip().split()
    meaningful = [tok for tok in tokens if tok.lower() not in FILLER_WORDS]
    return " ".join(meaningful).strip()


_GENERIC_SECTION_STOPWORDS: Set[str] = {
    "a",
    "an",
    "the",
    "this",
    "that",
    "each",
    "every",
    "from",
    "in",
    "on",
    "section",
    "heading",
    "date",
    "timeline",
}


def _detect_target_section(instruction: str) -> Optional[str]:
    """Detects whether the user instruction targets a specific page section (e.g. 'calendars')."""
    if not instruction:
        return None
    if re.search(r"\bcalendars?\b", instruction, re.IGNORECASE):
        return "calendars"

    match = re.search(r"\b([a-z]{3,})\s+section\b", instruction, re.IGNORECASE)
    if match:
        candidate = match.group(1).strip().lower()
        if candidate not in _GENERIC_SECTION_STOPWORDS:
            return candidate
    return None


def parse_instruction(instruction: str) -> ExtractionPlan:
    """
    Parses a natural language instruction into an ExtractionPlan with columns and group_by key.
    
    Args:
        instruction: Plain English user instructions (e.g. 'Collect tech events with date, time, name...').
        
    Returns:
        ExtractionPlan: Structured schema containing planned columns and group_by target.
    """
    if not instruction or not instruction.strip():
        instruction = "Collect items with Name and Link"

    raw_text = instruction.strip()

    # If the user used "with", the field list is usually after "with"
    if " with " in f" {raw_text.lower()} ":
        parts = re.split(r"\bwith\b", raw_text, flags=re.IGNORECASE)
        # Check if the part after "with" contains column specifications
        candidate_field_part = parts[-1]
    else:
        candidate_field_part = raw_text

    # Split by commas, "and", "&", or newlines
    split_chunks = re.split(r"[,;\n]|\band\b|&", candidate_field_part, flags=re.IGNORECASE)

    planned_columns: List[ColumnSpec] = []
    seen_names: Set[str] = set()

    for chunk in split_chunks:
        trimmed = chunk.strip()
        if not trimmed:
            continue

        # Try matching synonym directly on chunk
        canonical = match_synonym(trimmed)

        # If no match, try after filtering filler words
        cleaned_phrase = _clean_phrase(trimmed)
        if not canonical and cleaned_phrase:
            canonical = match_synonym(cleaned_phrase)

        if canonical:
            col_name = canonical
            data_type = COLUMN_DATA_TYPES.get(canonical, "string")
            description = f"Extracted {canonical}"
        elif cleaned_phrase:
            # Custom column: format as Title Case
            col_name = " ".join(word.capitalize() for word in cleaned_phrase.split())
            data_type = "string"
            description = f"Custom field: {col_name}"
        else:
            continue

        if col_name not in seen_names:
            seen_names.add(col_name)
            planned_columns.append(ColumnSpec(name=col_name, data_type=data_type, description=description))

    # If parsing yielded no columns, default to Name and Link
    if not planned_columns:
        planned_columns = [
            ColumnSpec(name="Name", data_type="string", description="Item title or headline"),
            ColumnSpec(name="Link", data_type="url", description="Source or registration link"),
        ]
        seen_names = {"Name", "Link"}

    # Always ensure "Source Website" column is present
    if "Source Website" not in seen_names:
        planned_columns.append(
            ColumnSpec(name="Source Website", data_type="url", description="Original website URL")
        )

    col_names = [c.name for c in planned_columns]

    # Choose group_by by deterministic priority:
    # 1. Date if requested
    # 2. Category if requested
    # 3. Company or Host if requested
    # 4. Location if requested
    # 5. First non-Link/non-Source column, or Name
    group_by = "Name"
    if "Date" in col_names:
        group_by = "Date"
    elif "Category" in col_names:
        group_by = "Category"
    elif "Company" in col_names:
        group_by = "Company"
    elif "Host" in col_names:
        group_by = "Host"
    elif "Location" in col_names:
        group_by = "Location"
    else:
        for c in col_names:
            if c not in ("Link", "Source Website"):
                group_by = c
                break

    target_section = _detect_target_section(raw_text)
    logger.info(
        f"Rule-based parser generated {len(planned_columns)} columns. "
        f"Group by: '{group_by}'. Target section: '{target_section}'."
    )
    return ExtractionPlan(
        instruction=instruction,
        columns=planned_columns,
        group_by=group_by,
        target_section=target_section,
    )


# Backwards compatibility alias
plan_schema = parse_instruction

# core/categorizer.py - Step 8: Categorization and grouping of extracted data rows.
# This file organizes flat rows into logical groups based on the plan's group_by column,
# sorting dates chronologically (oldest first) with non-date or missing values last.

from collections import defaultdict
from datetime import datetime
from typing import Any, Dict, List, Tuple
import pandas as pd
from models.schemas import Row
from utils.logger import logger


def _parse_category_sort_key(category_name: str) -> Tuple[int, Any]:
    """
    Parses a category label to create a sort key:
    Real dates formatted as DD-MM-YYYY sort oldest-first at priority 0.
    Other text or 'Uncategorized' sorts at priority 1.
    """
    # Try parsing DD-MM-YYYY format
    for fmt in ("%d-%m-%Y", "%Y-%m-%d", "%d/%m/%Y"):
        try:
            dt = datetime.strptime(category_name.strip(), fmt)
            return (0, dt)
        except ValueError:
            continue
    # Non-date categories sort alphabetically after all dates
    return (1, category_name.lower())


def categorize_rows(rows: List[Row], group_by: str) -> Dict[str, List[Row]]:
    """
    Groups rows by the value of a designated group_by column,
    sorting categories chronologically (oldest first) with non-dates placed last.
    
    Args:
        rows: List of extracted Row objects.
        group_by: Column name to group on (e.g., 'Date', 'Company', 'Category').
        
    Returns:
        Dict[str, List[Row]]: Ordered dictionary mapping category names to their rows.
    """
    grouped: Dict[str, List[Row]] = defaultdict(list)

    for row in rows:
        raw_val = row.data.get(group_by)
        # Normalize category key if empty or missing
        if raw_val is None or str(raw_val).strip() in ("", "Not found", "null", "None"):
            category_key = "Uncategorized"
        else:
            category_key = str(raw_val).strip()

        grouped[category_key].append(row)

    # Sort categories: valid dates oldest first, non-dates/uncategorized last
    sorted_keys = sorted(grouped.keys(), key=_parse_category_sort_key)
    sorted_grouped = {k: grouped[k] for k in sorted_keys}

    logger.info(f"Grouped {len(rows)} rows into {len(sorted_grouped)} categories using '{group_by}'.")
    return sorted_grouped


def rows_to_dataframe(rows: List[Row], columns: List[str]) -> pd.DataFrame:
    """
    Converts a list of Row objects into a clean pandas DataFrame with consistent columns.
    
    Args:
        rows: List of Row objects to convert.
        columns: Ordered list of column headers to display.
        
    Returns:
        pd.DataFrame: Tabular data with specified columns in order.
    """
    if not rows:
        return pd.DataFrame(columns=columns)

    records = []
    for r in rows:
        record = {col: r.data.get(col, "Not found") for col in columns}
        records.append(record)

    df = pd.DataFrame(records)
    for col in columns:
        if col not in df.columns:
            df[col] = "Not found"

    return df[columns]

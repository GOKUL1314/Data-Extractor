# core/exporter.py - Step 9: Multi-format data exporter (Excel, CSV, JSON).
# This file converts extracted and categorized records into Excel workbooks,
# CSV spreadsheets, and JSON files saved in the outputs/ directory.

from datetime import datetime
import json
from pathlib import Path
import re
from typing import Dict, List, Optional
import pandas as pd
from config import OUTPUTS_DIR
from core.categorizer import rows_to_dataframe
from models.schemas import Row
from utils.logger import logger


def _sanitize_sheet_name(name: str) -> str:
    r"""Excel sheet names must be <= 31 characters and cannot contain : \ / ? * [ ]"""
    cleaned = re.sub(r'[:\\/?*\[\]]', '_', name).strip()
    return cleaned[:31] if cleaned else "Sheet"


def export_to_csv(rows: List[Row], columns: List[str], filename: Optional[str] = None) -> Path:
    """
    Exports all extracted rows into a single CSV file.
    
    Args:
        rows: List of extracted Row objects.
        columns: Ordered list of column names.
        filename: Optional custom filename.
        
    Returns:
        Path: Absolute path of the generated CSV file.
    """
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    file_path = OUTPUTS_DIR / (filename or f"extracted_data_{ts}.csv")

    df = rows_to_dataframe(rows, columns)
    df.to_csv(file_path, index=False, encoding="utf-8-sig")
    logger.info(f"Exported {len(rows)} rows to CSV at: {file_path}")
    return file_path


def export_to_json(rows: List[Row], filename: Optional[str] = None) -> Path:
    """
    Exports all extracted rows into a formatted JSON file.
    
    Args:
        rows: List of extracted Row objects.
        filename: Optional custom filename.
        
    Returns:
        Path: Absolute path of the generated JSON file.
    """
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    file_path = OUTPUTS_DIR / (filename or f"extracted_data_{ts}.json")

    data = [r.data for r in rows]
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    logger.info(f"Exported {len(rows)} rows to JSON at: {file_path}")
    return file_path


def export_to_excel(
    grouped_data: Dict[str, List[Row]],
    all_rows: List[Row],
    columns: List[str],
    filename: Optional[str] = None,
) -> Path:
    """
    Exports categorized data to an Excel workbook with an 'All Data' sheet and category tabs.
    
    Args:
        grouped_data: Dictionary mapping categories to rows.
        all_rows: Complete list of all extracted rows.
        columns: Ordered list of column names.
        filename: Optional custom filename.
        
    Returns:
        Path: Absolute path of the generated Excel (.xlsx) file.
    """
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    file_path = OUTPUTS_DIR / (filename or f"extracted_data_{ts}.xlsx")

    with pd.ExcelWriter(file_path, engine="openpyxl") as writer:
        # Sheet 1: Master table with all records
        df_all = rows_to_dataframe(all_rows, columns)
        df_all.to_excel(writer, sheet_name="All Data", index=False)

        # Subsequent sheets: one per category
        used_names = {"All Data"}
        for category, cat_rows in grouped_data.items():
            base_name = _sanitize_sheet_name(category)
            sheet_name = base_name
            # Ensure unique sheet names if truncated names collide
            counter = 1
            while sheet_name in used_names:
                sheet_name = f"{base_name[:28]}_{counter}"
                counter += 1
            used_names.add(sheet_name)

            df_cat = rows_to_dataframe(cat_rows, columns)
            df_cat.to_excel(writer, sheet_name=sheet_name, index=False)

    logger.info(f"Exported Excel workbook with {len(used_names)} sheets at: {file_path}")
    return file_path

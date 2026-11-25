# core/pipeline.py - Orchestrator coordinating rule-based steps 1 through 9 in sequence.
# Ties together URL processing, rule-based classification, instruction parsing,
# page fetching (httpx/Playwright), multi-strategy extraction, standardization,
# categorization, and file exports deterministically.

from typing import Any, Callable, Dict, List, Optional, Set, Tuple
from core.categorizer import categorize_rows
from core.classifier import classify_site
from core.date_utils import standardize_row_dates, standardize_row_hosts, standardize_row_times
from core.exporter import export_to_csv, export_to_excel, export_to_json
from core.extractor import extract_rows_from_text
from core.fetcher import fetch_page
from core.instruction_parser import parse_instruction
from core.url_handler import explain_invalid_urls, process_url_input
from models.schemas import ExtractionPlan, Result, Row, SiteInfo
from utils.logger import logger


def deduplicate_rows_by_link(rows: List[Row], link_column: str = "Link") -> Tuple[List[Row], int]:
    """
    Deduplicates a list of Row objects based on their Link field.
    
    Args:
        rows: List of extracted Row objects.
        link_column: Name of the column containing the URL link.
        
    Returns:
        Tuple[List[Row], int]: (Deduplicated rows, Count of duplicate rows dropped).
    """
    unique_rows: List[Row] = []
    seen_links: Set[str] = set()
    dup_count = 0

    for r in rows:
        link_val = r.data.get(link_column)
        if link_val and link_val != "Not found":
            if link_val in seen_links:
                dup_count += 1
                continue
            seen_links.add(link_val)
        unique_rows.append(r)

    return unique_rows, dup_count


def run_pipeline(
    raw_urls: str,
    instruction: str,
    client: Optional[object] = None,
    manual_selectors: Optional[Dict[str, str]] = None,
    progress_callback: Optional[Callable[[str, float, Optional[Result]], None]] = None,
) -> Dict[str, Any]:
    """
    Executes the end-to-end rule-based extraction and categorization pipeline.
    
    Args:
        raw_urls: Multiline text of input URLs.
        instruction: Plain English description of data to extract.
        client: Ignored (kept for backwards compatibility).
        manual_selectors: Optional dict mapping column names to CSS selectors.
        progress_callback: Optional callback(message, progress_float, site_result).
        
    Returns:
        Dict[str, Any]: Pipeline results dictionary containing plan, site results,
                        categorized rows, all rows, and exported file paths.
    """
    logger.info("--- Starting Rule-Based Extraction Pipeline ---")

    def update_progress(msg: str, pct: float, res: Optional[Result] = None):
        if progress_callback:
            progress_callback(msg, pct, res)

    # Step 1: Input URL validation & deduplication
    update_progress("Step 1/9: Validating and cleaning URLs...", 0.05)
    urls = process_url_input(raw_urls)
    if not urls:
        raise ValueError(explain_invalid_urls(raw_urls))

    # Step 2: Parse user instruction into schema columns and group_by key
    update_progress("Step 2/9: Parsing instruction and schema...", 0.15)
    plan: ExtractionPlan = parse_instruction(instruction)
    col_names = [col.name for col in plan.columns]

    site_results: List[Result] = []
    all_rows: List[Row] = []

    # Process each website individually so one URL failure never stops the others
    total_sites = len(urls)
    for idx, url in enumerate(urls, start=1):
        site_progress_base = 0.20 + (0.60 * ((idx - 1) / total_sites))
        update_progress(f"Step 3/9: Fetching website ({idx}/{total_sites}): {url}", site_progress_base)

        try:
            # Step 4: Fetch page content using httpx fast-path or Playwright Chromium
            success, content_or_err = fetch_page(url)
            if not success:
                site_info = SiteInfo(url=url, site_type="unknown", reason=f"Fetch failed: {content_or_err}")
                res = Result(site_info=site_info, status="failed", rows=[], error_message=content_or_err)
                site_results.append(res)
                update_progress(f"Failed to fetch {url}", site_progress_base + (0.50 / total_sites), res)
                continue

            # Step 2: Classify site type via deterministic rules
            site_info = classify_site(url, content_or_err)

            # Step 6: Extract structured rows using multi-strategy rules
            update_progress(f"Step 6/9: Extracting data from {url}...", site_progress_base + (0.35 / total_sites))
            extracted, strategy_used, diagnostics = extract_rows_from_text(
                content_or_err,
                url,
                plan,
                manual_selectors=manual_selectors,
            )

            status = "success" if extracted else "failed"
            err_msg = None if extracted else "No matching records found with extraction strategies."
            res = Result(
                site_info=site_info,
                status=status,
                rows=extracted,
                error_message=err_msg,
                strategy_used=strategy_used,
                diagnostics=diagnostics,
            )
            site_results.append(res)
            all_rows.extend(extracted)
            update_progress(
                f"Completed {url}: {len(extracted)} rows extracted ({strategy_used}).",
                site_progress_base + (0.60 / total_sites),
                res,
            )

        except Exception as exc:
            logger.warning(f"Error processing URL '{url}': {exc}")
            site_info = SiteInfo(url=url, site_type="error", reason=str(exc))
            res = Result(site_info=site_info, status="failed", rows=[], error_message=str(exc))
            site_results.append(res)
            update_progress(f"Error on {url}: {exc}", site_progress_base + (0.60 / total_sites), res)

    # Global deduplication across all extracted rows by Link
    all_rows, dropped_duplicates = deduplicate_rows_by_link(all_rows, link_column="Link")
    if dropped_duplicates > 0:
        logger.info(f"Deduplicated {dropped_duplicates} identical records across sites.")

    # If 0 rows were extracted across all sites, do not create export files
    if not all_rows:
        logger.warning("Pipeline finished with 0 total extracted rows. Skipping file exports.")
        update_progress("Extraction finished: 0 records found.", 1.0)
        return {
            "plan": plan,
            "site_results": site_results,
            "all_rows": [],
            "grouped_rows": {},
            "columns": col_names,
            "csv_path": None,
            "json_path": None,
            "excel_path": None,
            "duplicates_removed": dropped_duplicates,
        }

    # Step 7: Standardize relative date labels to DD-MM-YYYY using system clock
    date_cols = [c.name for c in plan.columns if "date" in c.name.lower()]
    for date_col in date_cols:
        standardize_row_dates(all_rows, date_column=date_col)

    # Standardize 12-hour times to 24-hour HH:MM format
    time_cols = [c.name for c in plan.columns if "time" in c.name.lower()]
    for time_col in time_cols:
        standardize_row_times(all_rows, time_column=time_col)

    # Standardize host names by stripping leading "By "
    host_cols = [c.name for c in plan.columns if "host" in c.name.lower() and "link" not in c.name.lower()]
    for host_col in host_cols:
        standardize_row_hosts(all_rows, host_column=host_col)

    # Step 8: Categorize rows by group_by column (oldest dates first)
    update_progress("Step 8/9: Categorizing extracted records...", 0.85)
    grouped_rows = categorize_rows(all_rows, plan.group_by)

    # Step 9: Export to Excel, CSV, and JSON
    update_progress("Step 9/9: Generating export files...", 0.95)
    csv_path = export_to_csv(all_rows, col_names)
    json_path = export_to_json(all_rows)
    excel_path = export_to_excel(grouped_rows, all_rows, col_names)

    update_progress("Extraction complete!", 1.0)
    logger.info(f"--- Pipeline Finished: {len(all_rows)} total rows across {len(grouped_rows)} categories ---")

    return {
        "plan": plan,
        "site_results": site_results,
        "all_rows": all_rows,
        "grouped_rows": grouped_rows,
        "columns": col_names,
        "csv_path": str(csv_path),
        "json_path": str(json_path),
        "excel_path": str(excel_path),
        "duplicates_removed": dropped_duplicates,
    }

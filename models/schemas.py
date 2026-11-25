# models/schemas.py - Data classes for the entire application.
# Defines the standard shapes of data moving between pipeline steps,
# ensuring type safety and clarity across modules without external dependencies.

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ColumnSpec:
    """
    Defines the specification for an extracted table column.
    
    Attributes:
        name: Clean, human-readable column name (e.g., 'Name', 'Date').
        data_type: Expected data type ('string', 'date', 'time', 'number', 'url').
        description: Short explanation of what belongs in this column.
    """
    name: str
    data_type: str = "string"
    description: str = ""


@dataclass
class ExtractionPlan:
    """
    The structured plan created from user instructions.
    
    Attributes:
        instruction: The original user instruction in plain English.
        columns: List of columns to extract.
        group_by: Name of the single column used for grouping/categorization.
        target_section: Optional section target noun (e.g., 'calendars') for section-scoped extraction.
    """
    instruction: str
    columns: List[ColumnSpec]
    group_by: str
    target_section: Optional[str] = None


@dataclass
class SiteInfo:
    """
    Information and classification results for a single target URL.
    
    Attributes:
        url: The normalized website URL.
        site_type: Detected category (events, jobs, news, education, ecommerce, other).
        reason: Explanation of which deterministic rule matched.
    """
    url: str
    site_type: str = "other"
    reason: str = ""


@dataclass
class Row:
    """
    A single extracted record from a website.
    
    Attributes:
        data: Key-value dictionary containing the extracted column values.
        source_url: The top-level website URL where the item was found.
        detail_url: The sub-page URL if detail following was used.
    """
    data: Dict[str, Any]
    source_url: str
    detail_url: Optional[str] = None


@dataclass
class Result:
    """
    The overall extraction result for a single target website.
    
    Attributes:
        site_info: Information about the processed site.
        status: Status code: 'success', 'partial', or 'failed'.
        rows: List of extracted data rows.
        error_message: Failure explanation if the site could not be processed.
        strategy_used: Name of the extraction strategy that produced the rows.
        diagnostics: Diagnostic details if extraction produced 0 rows.
    """
    site_info: SiteInfo
    status: str  # "success", "partial", "failed"
    rows: List[Row] = field(default_factory=list)
    error_message: Optional[str] = None
    strategy_used: Optional[str] = None
    diagnostics: Optional[Dict[str, Any]] = None

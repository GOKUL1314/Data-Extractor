# 📝 Project Setup and Architecture Notes

This document provides a quick-reference guide detailing all installed libraries, prerequisites, installation steps, and instructions for running the 100% rule-based Multi-Website Data Extractor project.

---

## 1. Installed Packages & Libraries

Below is the list of third-party libraries used in this project and their specific roles:

| Package / Library | Version | Purpose in this Project |
| :--- | :--- | :--- |
| **`streamlit`** | `>=1.30.0` | **Web UI & Dashboard**: Provides the browser interface, input text areas, manual CSS selector inputs, real-time progress indicators, interactive data tables, category tabs, and file download buttons. |
| **`httpx`** | `>=0.25.0` | **Fast-Path HTTP Client**: Performs fast static HTML downloads for plain websites (e.g. Hacker News, static job boards) before falling back to browser rendering. |
| **`playwright`** | `>=1.40.0` | **Headless Browser Rendering**: Launches headless Chromium to render JavaScript-heavy single-page apps (Next.js/React), bypass dynamic rendering issues, and scroll lazy-loaded content. |
| **`beautifulsoup4`** | `>=4.12.0` | **HTML Parsing & Extraction**: Traverses DOM structures, extracts JSON-LD and embedded JSON scripts, detects repeated card containers, and parses tables. |
| **`lxml`** | `>=4.9.0` | **High-Speed HTML/XML Parser**: High-performance C-based backend parser used by BeautifulSoup for fast parsing of large rendered DOM trees. |
| **`requests`** | `>=2.31.0` | **HTTP Client**: Standard HTTP utilities library. |
| **`pandas`** | `>=2.1.0` | **Data Manipulation**: Converts extracted data into structured DataFrames for tabular display and data alignment across categories. |
| **`openpyxl`** | `>=3.1.0` | **Excel File Generator**: Enables creating multi-tab `.xlsx` workbooks containing an **All Data** sheet alongside individual tabs for each category. |
| **`python-dotenv`** | `>=1.0.0` | **Optional Environment Config**: Optionally loads local environment overrides if present (no `.env` file is required). |
| **`pytest`** | `>=8.0.0` | **Automated Testing**: Offline unit testing framework that validates URL cleaning, instruction parsing, field detectors, extraction strategies, grouping, deduplication, and exports. |

---

## 2. What Must Be Installed Before Running?

Before starting the application, ensure the following prerequisites are installed:

### A. Python (Version 3.11 or higher)
Ensure Python is installed and added to your system PATH:
```powershell
python --version
```

### B. Virtual Environment (Recommended)
Create and activate an isolated environment so dependencies don't conflict:

* **Windows (PowerShell):**
  ```powershell
  python -m venv venv
  .\venv\Scripts\Activate.ps1
  ```
* **Windows (Command Prompt):**
  ```cmd
  python -m venv venv
  venv\Scripts\activate.bat
  ```
* **macOS / Linux:**
  ```bash
  python3 -m venv venv
  source venv/bin/activate
  ```

### C. Install Python Dependencies
Install all required libraries listed in `requirements.txt`:
```powershell
pip install -r requirements.txt
```

### D. Install Playwright Browser Binaries
Playwright requires browser binaries to be downloaded separately after installing the Python package:
```powershell
playwright install chromium
```
*(Only Chromium is required for this project).*

> **Note:** No external accounts, tokens, or `.env` configuration files are required. Everything runs 100% locally using deterministic rules.

---

## 3. How to Run the Project

### Step 1: Start the Streamlit Application
In your terminal (with your virtual environment activated), run:
```powershell
python -m streamlit run app.py
```

### Step 2: Access the Web Interface
Open your web browser and go to the URL printed in the terminal (typically):
```
http://localhost:8501
```

### Step 3: Extract Data
1. **Enter Website URLs:**
   In **Website URLs**, enter one or more target website URLs (one per line), e.g.:
   ```text
   https://lu.ma/sf
   https://news.ycombinator.com
   https://realpython.github.io/fake-jobs/
   ```
2. **Enter Extraction Instruction:**
   In **What data do you want to extract?**, describe the fields you want in plain English:
   * Events example: `Collect upcoming tech events with date, time, event name, host, location and registration link`
   * Section-targeted example (e.g. Luma Popular Calendars): `calendar name, description, link` (or `<noun> section`, such as `Collect sponsors section with name, link`)
3. **(Optional) Manual CSS Selectors:**
   Expand **🎯 Manual CSS Selectors (Optional)** to specify exact CSS selectors (e.g., `.job-title`, `.company`) for any column if you want to override automatic detection rules.
4. Click **🚀 Extract & Categorize**.

### Step 4: View & Export Results
* Inspect the rule-parsed schema, matched site classification, active extraction strategy, and category tables in the browser tabs.
* Click **Download Excel (.xlsx)**, **Download CSV**, or **Download JSON** to save the extracted data locally to your machine.

---

## 4. How to Run Automated Unit Tests

To verify that all modules (URL handler, instruction parser, field detectors, extraction strategies, categorizer, date utils, exporter) are working properly offline:
```powershell
python -m pytest tests/
```
All 36 offline unit tests use local HTML fixtures under `tests/fixtures/` (including `tests/fixtures/luma_calendars.html` for section-targeted calendar extraction). Running `tests/` directly avoids collecting the live integration script `test_live_runner.py` in the project root.

---

## 5. Section-Targeted Extraction & Diagnostics

* **Target Section Detection (`core/instruction_parser.py` & `models/schemas.py`)**: Instructions mentioning `calendar`/`calendars` set `ExtractionPlan.target_section = "calendars"` (and `<noun> section` sets `target_section` to `<noun>`).
* **Section Scoping (`core/extractor.py`)**: When `target_section` is set, extraction runs `_extract_calendar_cards()` (or generic `_extract_section_cards()`) first and does **not** fall through to event/page strategies:
  * Locates the section heading (e.g. `"Popular Calendars in San Francisco"`), scopes to the tightest container holding the section's cards, and collects Luma calendar anchors (`?k=c`).
  * Builds `Name` (first meaningful text line excluding `"Follow"`), `Description` (remaining text), and `Link` (absolute URL with `?k=c` stripped).
  * In normal events mode (`target_section=None`), `?k=c` / calendar-section anchors are excluded so they do not pollute event rows.
* **0-Row & Render Diagnostics**:
  * When section-targeted extraction returns 0 rows, `diagnostics` reports `section_heading_found` and `candidate_anchors_seen`.
  * Use `python scripts/debug_fetch.py <url>` to render a page with Playwright, scroll until height stabilizes, save `outputs/debug_<domain>.html`, and inspect matching sections, `?k=c` anchors, and JSON/XHR responses.

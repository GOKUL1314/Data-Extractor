# 🌐 Multi-Website Data Extractor (Rule-Based)

A fast, 100% local, rule-based Python tool that fetches websites using `httpx` (fast path) and `Playwright` (headless Chromium fallback), parses plain-English field instructions into columns using deterministic synonym rules, extracts structured records via multi-strategy DOM/JSON heuristics, categorizes them chronologically or logically, and exports ready-to-use Excel, CSV, and JSON reports in Streamlit.

> **Note on Architecture:** The Gemini API and all external LLM dependencies (`google-genai`, `llm/`) have been completely removed. No API keys or `.env` files are required to run this application.

---

## ✨ Features

- **100% Offline Rule-Based Engine**: Zero API keys, zero external model calls, and zero rate limits.
- **Deterministic Instruction Parser**: Splits plain-English requests into clean schema columns via an editable synonyms dictionary (`core/synonyms.py`) and selects the optimal grouping column.
- **Hybrid Fast-Path Fetching**: Uses `httpx` for instant static page fetching and automatically escalates to headless Playwright Chromium (with scroll virtualization preservation) for JavaScript-heavy apps.
- **6-Stage Extraction Cascade + Section-Targeted Mode**:
  0. **Section-Targeted Mode** (runs first without falling through when the prompt targets a section such as `"calendar name, description, link"` or `"<noun> section"`, scoping from heading keyword -> container -> repeated cards)
  1. **JSON-LD** (`<script type="application/ld+json">`)
  2. **Embedded JSON** (`__NEXT_DATA__`, `__INITIAL_STATE__`)
  3. **Repeated DOM Cards** (using regex & positional field detectors, excluding calendar `?k=c` anchors in normal events mode)
  4. **Heading Sections** (date headings sitting above card groups)
  5. **Label Rules** (`Label: value` lines and list headings)
  6. **HTML Tables** (`<table>` headers & rows)
- **Manual CSS Selector Mode**: Optional per-column CSS selector boxes in the UI to override automatic detection rules whenever needed.
- **Diagnostic Reporting**: Clearly explains page text length, potential login/bot walls, and strategies tried when no matching records are found.
- **Multi-Format Export**: Generates Excel workbooks (`.xlsx` with **All Data** + per-category sheets), UTF-8 CSV, and formatted JSON.

---

## 🛠️ Tech Stack

- **Python**: 3.11+
- **Frontend / UI**: [Streamlit](https://streamlit.io/)
- **Fetching**: `httpx` (static fast-path), `Playwright` (Chromium JS rendering)
- **Parsing**: `BeautifulSoup4` with `lxml` parser
- **Data & Exports**: `pandas` and `openpyxl`
- **Testing**: `pytest`

---

## 🚀 Installation & Setup

### 1. Open the Project
```powershell
cd c:\Users\GOKUL\Desktop\data-extractor
```

### 2. Create and Activate a Virtual Environment
```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

### 3. Install Python Dependencies & Playwright Chromium
```powershell
pip install -r requirements.txt
playwright install chromium
```
*(No `.env` file or API key setup is needed.)*

---

## 💻 Running the Application

Launch the Streamlit web dashboard:
```powershell
python -m streamlit run app.py
```
Your browser will open at `http://localhost:8501`.

1. Enter one or more website URLs (one per line) in **Website URLs** (e.g. `https://lu.ma/sf`).
2. Describe the fields you want in **What data do you want to extract?** (e.g. `"Collect upcoming tech events with date, time, event name, host, location and registration link"`).
3. *(Optional)* Expand **Manual CSS Selectors** to specify custom selectors (like `.job-title`) for any column.
4. Click **🚀 Extract & Categorize**.
5. View the rule-parsed schema, site classification rule, active extraction strategy, and categorized tabs.
6. Download your results as **Excel (.xlsx)**, **CSV**, or **JSON**.

---

## 🧪 Running Unit Tests

Run the offline unit test suite (using local HTML fixtures in `tests/fixtures/`):
```powershell
python -m pytest
```

---

## 📚 Learning Guide

To understand the new rule-based data flow, extraction strategies, and how to customize synonyms or add new rules, read [CODE_GUIDE.md](CODE_GUIDE.md).

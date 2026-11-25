# app.py - Streamlit User Interface for the Rule-Based Data Extraction Tool.
# Provides a 100% local, rule-based web scraper with automatic schema parsing,
# multi-strategy extraction, optional manual CSS selectors, and multi-format exports.

from pathlib import Path
from typing import Dict, Optional
import streamlit as st
import config
from core.categorizer import rows_to_dataframe
from core.instruction_parser import parse_instruction
from core.pipeline import run_pipeline
from utils.logger import logger

# Set up page styling and layout
st.set_page_config(
    page_title="Rule-Based Data Extractor",
    page_icon="🔍",
    layout="wide",
)


def render_sidebar():
    """Renders the settings and information sidebar without any external models."""
    st.sidebar.header("⚙️ Rule-Based Engine")
    st.sidebar.success("🔒 **100% Local Execution**\nFully deterministic rule-based scraper.")

    st.sidebar.markdown("---")
    st.sidebar.subheader("Active Extraction Strategies")
    st.sidebar.markdown(
        """
1. **JSON-LD** (`<script type="application/ld+json">`)
2. **Embedded JSON** (`__NEXT_DATA__`, etc.)
3. **Repeated Cards** (structural heuristics)
4. **Heading Sections** (date-grouped runs)
5. **Label Rules** (`Label: value` lines)
6. **HTML Tables** (`<table>` rows)
        """
    )

    st.sidebar.markdown("---")
    st.sidebar.markdown(
        f"⏱️ **Timeout:** `{config.REQUEST_TIMEOUT_SECONDS}s`  \n"
        f"📜 **Max Scrolls:** `{config.MAX_SCROLLS}`"
    )

    st.sidebar.markdown("---")
    st.sidebar.markdown(
        "💡 **Tip**: Enter any URLs (events, jobs, products, news) and describe what fields you need in natural English."
    )


def render_input_form():
    """Renders the input text areas, manual CSS selectors, and the Extract trigger button."""
    st.subheader("1. Enter Websites & Instruction")

    col1, col2 = st.columns([1, 1])

    with col1:
        default_urls = "https://lu.ma/sf"
        raw_urls = st.text_area(
            "Website URLs (one per line):",
            value=default_urls,
            height=130,
            placeholder="https://example.com/events\nhttps://example.com/jobs",
        )

    with col2:
        default_prompt = (
            "Collect upcoming tech events with date, time, event name, "
            "host, location and registration link"
        )
        instruction = st.text_area(
            "What data do you want to extract?",
            value=default_prompt,
            height=130,
            placeholder="e.g. Collect developer jobs with job title, company, location, link, required skills",
        )

    # Preview planned columns to allow manual CSS selector overrides
    preview_plan = parse_instruction(instruction)
    manual_selectors: Dict[str, str] = {}

    with st.expander("🎯 Manual CSS Selectors (Optional)", expanded=False):
        st.markdown(
            "Type a custom CSS selector (e.g. `.job-title`, `a.titleline`, `span.company`) "
            "for any column to override automatic heuristic rules."
        )
        cols_ui = st.columns(min(len(preview_plan.columns), 3) or 1)
        for idx, col_spec in enumerate(preview_plan.columns):
            if col_spec.name == "Source Website":
                continue
            with cols_ui[idx % len(cols_ui)]:
                val = st.text_input(
                    f"Selector for '{col_spec.name}':",
                    placeholder="e.g. .event-title",
                    key=f"selector_{col_spec.name}",
                )
                if val.strip():
                    manual_selectors[col_spec.name] = val.strip()

    extract_button = st.button("🚀 Extract & Categorize", type="primary", width="stretch")
    return raw_urls, instruction, manual_selectors, extract_button


def render_plan_summary(plan):
    """Displays the rule-parsed schema columns and grouping key."""
    st.subheader("2. Rule-Parsed Schema")
    st.markdown(f"**Grouping Column (Categorizer):** `{plan.group_by}`")

    cols = [{"Column Name": c.name, "Type": c.data_type, "Description": c.description} for c in plan.columns]
    st.dataframe(cols, width="stretch", hide_index=True)


def render_site_statuses(site_results):
    """Displays the status, strategy, and diagnostics for each processed URL."""
    st.subheader("3. Website Processing Status")

    for res in site_results:
        site = res.site_info
        badge = "🟢 Success" if res.status == "success" else ("🟡 Partial" if res.status == "partial" else "🔴 Failed")
        with st.expander(f"{badge} — {site.url} (Type: {site.site_type})", expanded=True):
            st.write(f"**Classification:** {site.site_type.title()} — `{site.reason}`")
            st.write(f"**Strategy Used:** `{res.strategy_used or 'None'}`")
            st.write(f"**Records Found:** {len(res.rows)}")

            if res.error_message:
                st.warning(f"Status Note: {res.error_message}")

            # If no rows extracted, show full diagnostic breakdown
            if not res.rows and res.diagnostics:
                diag = res.diagnostics
                st.error("⚠️ **No records were extracted from this page.**")
                if diag.get("is_block_or_login"):
                    st.error(f"🚨 **Block / Login Wall Detected:** {diag.get('block_reason')}")
                extra_diag = ""
                if "section_heading_found" in diag:
                    extra_diag = (
                        f"\n\n🧭 **Section Heading Found:** {diag.get('section_heading_found')}"
                        f"\n\n🔗 **Candidate Anchors Seen:** {diag.get('candidate_anchors_seen', 0)}"
                    )
                st.info(
                    f"📄 **Page Text Length:** {diag.get('text_length', 0)} characters\n\n"
                    f"🔍 **Strategies Attempted:**\n" + "\n".join(f"- {s}" for s in diag.get("strategies_tried", []))
                    + extra_diag
                )


def render_results(results_data):
    """Renders the categorized tables and export download buttons from session state."""
    plan = results_data["plan"]
    grouped_rows = results_data["grouped_rows"]
    all_rows = results_data["all_rows"]
    columns = results_data["columns"]

    st.subheader("4. Extracted Data Results")

    # If no records were extracted, show warning and skip download buttons
    if not all_rows:
        st.warning("⚠️ No records were extracted from the submitted page(s). Export files were not created.")
        return

    # Download Buttons row
    col_dl1, col_dl2, col_dl3 = st.columns(3)
    excel_path = Path(results_data["excel_path"]) if results_data.get("excel_path") else None
    csv_path = Path(results_data["csv_path"]) if results_data.get("csv_path") else None
    json_path = Path(results_data["json_path"]) if results_data.get("json_path") else None

    if excel_path and excel_path.exists():
        with open(excel_path, "rb") as f:
            col_dl1.download_button(
                label="📥 Download Excel (.xlsx)",
                data=f.read(),
                file_name=excel_path.name,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                width="stretch",
            )

    if csv_path and csv_path.exists():
        with open(csv_path, "rb") as f:
            col_dl2.download_button(
                label="📥 Download CSV",
                data=f.read(),
                file_name=csv_path.name,
                mime="text/csv",
                width="stretch",
            )

    if json_path and json_path.exists():
        with open(json_path, "rb") as f:
            col_dl3.download_button(
                label="📥 Download JSON",
                data=f.read(),
                file_name=json_path.name,
                mime="application/json",
                width="stretch",
            )

    # Tabbed view: One tab for All Data, followed by tabs for each category
    tab_titles = ["All Data"] + list(grouped_rows.keys())
    tabs = st.tabs(tab_titles)

    # Master 'All Data' Tab
    with tabs[0]:
        st.write(f"Total Records: **{len(all_rows)}**")
        df_all = rows_to_dataframe(all_rows, columns)
        st.dataframe(df_all, width="stretch")

    # Individual Category Tabs
    for i, (cat_name, cat_rows) in enumerate(grouped_rows.items(), start=1):
        with tabs[i]:
            st.write(f"Category: **{cat_name}** ({len(cat_rows)} items)")
            df_cat = rows_to_dataframe(cat_rows, columns)
            st.dataframe(df_cat, width="stretch")


def main():
    """Main application loop."""
    st.title("🌐 Multi-Website Data Extractor (100% Rule-Based)")
    st.markdown(
        "Extract structured information from any website using deterministic structural rules. "
        "No external model dependencies, fully offline-capable."
    )

    render_sidebar()
    raw_urls, instruction, manual_selectors, extract_button = render_input_form()

    # When the user clicks Extract, run the pipeline and save results to session state
    if extract_button:
        if not raw_urls.strip():
            st.error("Please enter at least one URL.")
            return

        if not instruction.strip():
            st.error("Please provide an extraction instruction.")
            return

        progress_bar = st.progress(0.0)
        status_text = st.empty()

        def on_progress(message: str, pct: float, site_res=None):
            progress_bar.progress(pct)
            status_text.info(f"⏳ {message}")

        try:
            with st.spinner("Processing websites with rule-based strategies..."):
                results = run_pipeline(
                    raw_urls=raw_urls,
                    instruction=instruction,
                    manual_selectors=manual_selectors,
                    progress_callback=on_progress,
                )

            st.session_state["pipeline_results"] = results
            if results.get("all_rows"):
                status_text.success(f"✅ Extraction completed successfully! ({len(results['all_rows'])} rows)")
            else:
                status_text.warning("Extraction completed: 0 records found.")
            progress_bar.progress(1.0)

        except Exception as exc:
            logger.error(f"Pipeline run encountered an error: {exc}")
            st.error(f"❌ Extraction Failed: {exc}")

    # Render previous or current results from session_state
    if "pipeline_results" in st.session_state:
        results_data = st.session_state["pipeline_results"]
        render_plan_summary(results_data["plan"])
        render_site_statuses(results_data["site_results"])
        render_results(results_data)


if __name__ == "__main__":
    main()

"""
Streamlit page for extracting Normalstunden values from invoice PDFs in a folder.
"""

from __future__ import annotations

from datetime import datetime
from io import BytesIO
from pathlib import Path
import re

import pandas as pd
import streamlit as st

from utils.invoice_normalstunden_extractor import (
    extract_normalstunden_from_pdf,
    list_pdf_files,
)

ILLEGAL_EXCEL_CHARACTERS_RE = re.compile(r"[\x00-\x08\x0B-\x0C\x0E-\x1F]")


def render_invoice_normalstunden_extraction_page() -> None:
    """Render folder-based invoice Normalstunden extraction page."""

    col1, col2 = st.columns([1, 3])
    with col1:
        if st.button("← Back to Dashboard", width="stretch"):
            st.session_state.current_page = "dashboard"
            st.rerun()

    st.title("Invoice Normalstunden Extraction")
    st.markdown(
        """
        Scan all PDFs in the `input` folder (or another local folder) and extract:
        - **Lieferant**
        - **Std./Menge** (total normal hours)
        - **Std.-Satz**

        Only regular hours are included. Zuschläge (weekend/night/holiday, etc.) are ignored.
        """
    )

    project_root = Path(__file__).resolve().parents[2]
    #default_input_path = str(project_root / "input")
    default_input_path = ""

    folder_path = st.text_input(
        "Input folder path",
        value=st.session_state.get("normalstunden_input_path", default_input_path),
    )
    recursive = st.checkbox("Include subfolders", value=True)

    if st.button("🚀 Extract Normalstunden", type="primary"):
        st.session_state.normalstunden_input_path = folder_path
        _process_folder(Path(folder_path), recursive=recursive)

    if st.session_state.get("normalstunden_results"):
        _display_results(st.session_state.normalstunden_results)


def _process_folder(folder_path: Path, recursive: bool) -> None:
    """Process all invoice PDFs in folder and store extraction results in session."""

    if not folder_path.exists() or not folder_path.is_dir():
        st.error(f"Folder not found: `{folder_path}`")
        return

    pdf_files = list_pdf_files(folder_path, recursive=recursive)
    if not pdf_files:
        st.warning("No PDF files found in the selected folder.")
        return

    st.session_state.normalstunden_results = []
    progress_bar = st.progress(0)
    status_text = st.empty()

    for idx, pdf_path in enumerate(pdf_files):
        status_text.text(f"Processing {pdf_path.name} ({idx + 1}/{len(pdf_files)})")
        progress_bar.progress((idx + 1) / len(pdf_files))

        try:
            result = extract_normalstunden_from_pdf(pdf_path)
        except Exception as exc:  # noqa: BLE001
            result = {
                "file_name": pdf_path.name,
                "file_path": str(pdf_path),
                "supplier": pdf_path.parent.name,
                "supplier_folder": pdf_path.parent.name,
                "hours_total": None,
                "hourly_rate_display": "",
                "entries": [],
                "status": "failed",
                "matched_rows": 0,
                "error": str(exc),
            }

        st.session_state.normalstunden_results.append(result)

    status_text.text("✅ Extraction complete")


def _display_results(results: list[dict]) -> None:
    """Display extraction summary, detailed table, and Excel export button."""

    st.markdown("---")
    st.markdown("## Results")

    total = len(results)
    success = sum(1 for row in results if row.get("status") == "success")
    no_match = sum(1 for row in results if row.get("status") == "no_match")
    failed = total - success - no_match

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total PDFs", total)
    with col2:
        st.metric("Extracted", success)
    with col3:
        st.metric("No Match", no_match)
    with col4:
        st.metric("Failed", failed)

    table_rows = []
    export_rows = []

    for row in results:
        hours_value = row.get("hours_total")
        hours_display = _format_optional_german_number(hours_value)

        status = row.get("status", "unknown")
        if status == "success":
            status_label = "✅ Extracted"
        elif status == "no_match":
            status_label = "⚠️ No Normalstunden Found"
        else:
            status_label = "❌ Failed"

        if status == "success":
            entries = row.get("entries", [])

            if entries:
                for entry in entries:
                    entry_hours_display = entry.get("hours_display") or hours_display
                    entry_rate_display = entry.get("hourly_rate_display") or row.get("hourly_rate_display", "")

                    table_rows.append(
                        {
                            "Datei": row.get("file_name", ""),
                            "Lieferant": row.get("supplier", ""),
                            "Lieferant (Ordnername)": row.get("supplier_folder", ""),
                            "Std./Menge": entry_hours_display,
                            "Std.-Satz": entry_rate_display,
                            "Status": status_label,
                        }
                    )

                    export_rows.append(
                        {
                            "Lieferant": row.get("supplier", ""),
                            "Lieferant (Ordnername)": row.get("supplier_folder", ""),
                            "Std./Menge": entry_hours_display,
                            "Std.-Satz": entry_rate_display,
                        }
                    )
            else:
                table_rows.append(
                    {
                        "Datei": row.get("file_name", ""),
                        "Lieferant": row.get("supplier", ""),
                        "Lieferant (Ordnername)": row.get("supplier_folder", ""),
                        "Std./Menge": hours_display,
                        "Std.-Satz": row.get("hourly_rate_display", ""),
                        "Status": status_label,
                    }
                )

                export_rows.append(
                    {
                        "Lieferant": row.get("supplier", ""),
                        "Lieferant (Ordnername)": row.get("supplier_folder", ""),
                        "Std./Menge": hours_display,
                        "Std.-Satz": row.get("hourly_rate_display", ""),
                    }
                )
        else:
            table_rows.append(
                {
                    "Datei": row.get("file_name", ""),
                    "Lieferant": row.get("supplier", ""),
                    "Lieferant (Ordnername)": row.get("supplier_folder", ""),
                    "Std./Menge": hours_display,
                    "Std.-Satz": row.get("hourly_rate_display", ""),
                    "Status": status_label,
                }
            )

    display_df = pd.DataFrame(table_rows)
    st.dataframe(display_df, width="stretch", hide_index=True)

    if export_rows:
        export_df = pd.DataFrame(export_rows)
        excel_bytes = _to_excel_bytes(export_df)
        filename = f"normalstunden_extraction_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"

        st.download_button(
            label="📥 Download Excel",
            data=excel_bytes,
            file_name=filename,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )


def _to_excel_bytes(df: pd.DataFrame) -> bytes:
    """Convert DataFrame to Excel bytes."""
    clean_df = _sanitize_dataframe_for_excel(df)

    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        clean_df.to_excel(writer, index=False, sheet_name="Normalstunden")
    output.seek(0)
    return output.getvalue()


def _format_optional_german_number(value: float | None) -> str:
    if value is None:
        return ""
    return f"{value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _sanitize_dataframe_for_excel(df: pd.DataFrame) -> pd.DataFrame:
    """Remove illegal control characters from string cells before Excel export."""
    clean_df = df.copy()
    object_columns = clean_df.select_dtypes(include=["object"]).columns

    for column in object_columns:
        clean_df[column] = clean_df[column].map(_sanitize_excel_string)

    return clean_df


def _sanitize_excel_string(value):
    if isinstance(value, str):
        return ILLEGAL_EXCEL_CHARACTERS_RE.sub("", value)
    return value

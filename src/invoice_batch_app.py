"""Local Streamlit UI for batch invoice CSV extraction."""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pandas as pd
import streamlit as st
from dotenv import load_dotenv


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
for path in (REPO_ROOT, SRC_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

load_dotenv(REPO_ROOT / ".env")

from scripts.process_invoices_to_csv import (  # noqa: E402
    append_rows,
    ensure_output_file,
    find_pdf_files,
    load_existing_statuses,
    process_pdf,
    should_skip_file,
)
from config.settings import azure_config  # noqa: E402


def main() -> None:
    st.set_page_config(page_title="Invoice Batch Processor", layout="wide")
    st.title("Invoice Batch Processor")
    st.caption("Run `scripts/process_invoices_to_csv.py` through a local UI.")

    if not azure_config.is_configured:
        st.warning(
            "Azure OpenAI is not configured. Create a `.env` file with "
            "`AZURE_OPENAI_API_KEY` and `AZURE_OPENAI_ENDPOINT`, then restart this app."
        )

    default_input = REPO_ROOT / "input"
    default_output = REPO_ROOT / "invoice_results_table.csv"

    with st.container(border=True):
        st.subheader("Settings")
        input_dir_text = st.text_input("Input folder with invoice PDFs", value=str(default_input))
        output_path_text = st.text_input("Output CSV file", value=str(default_output))

        col1, col2, col3 = st.columns(3)
        with col1:
            recursive = st.checkbox("Include subfolders", value=True)
            resume = st.checkbox("Resume / skip existing CSV rows", value=True)
        with col2:
            retry_failed = st.checkbox("Retry previously failed files", value=False)
            retries = st.number_input("AI retries per file", min_value=0, max_value=10, value=2, step=1)
        with col3:
            retry_delay_seconds = st.number_input(
                "Delay between AI retries (seconds)", min_value=0.0, value=10.0, step=1.0
            )
            delay_seconds = st.number_input(
                "Delay after each file (seconds)", min_value=0.0, value=0.0, step=0.5
            )

    input_dir = Path(input_dir_text).expanduser().resolve()
    output_path = Path(output_path_text).expanduser().resolve()

    col1, col2 = st.columns([1, 4])
    with col1:
        scan_clicked = st.button("Scan Folder", width="stretch")
    with col2:
        run_clicked = st.button("Process Invoices", type="primary", width="stretch")

    if scan_clicked:
        _scan_folder(input_dir, recursive)

    if run_clicked:
        _run_batch(
            input_dir=input_dir,
            output_path=output_path,
            recursive=recursive,
            resume=resume,
            retry_failed=retry_failed,
            retries=int(retries),
            retry_delay_seconds=float(retry_delay_seconds),
            delay_seconds=float(delay_seconds),
        )

    _show_existing_csv(output_path)


def _scan_folder(input_dir: Path, recursive: bool) -> None:
    if not input_dir.exists() or not input_dir.is_dir():
        st.error(f"Input folder not found: `{input_dir}`")
        return

    pdf_files = find_pdf_files(input_dir, recursive)
    if not pdf_files:
        st.warning(f"No PDF files found in `{input_dir}`.")
        return

    st.success(f"Found {len(pdf_files)} PDF file(s).")
    st.dataframe(
        pd.DataFrame({"PDF": [pdf.relative_to(input_dir).as_posix() for pdf in pdf_files]}),
        hide_index=True,
        width="stretch",
    )


def _run_batch(
    *,
    input_dir: Path,
    output_path: Path,
    recursive: bool,
    resume: bool,
    retry_failed: bool,
    retries: int,
    retry_delay_seconds: float,
    delay_seconds: float,
) -> None:
    if not input_dir.exists() or not input_dir.is_dir():
        st.error(f"Input folder not found: `{input_dir}`")
        return

    pdf_files = find_pdf_files(input_dir, recursive)
    if not pdf_files:
        st.warning(f"No PDF files found in `{input_dir}`.")
        return

    ensure_output_file(output_path)
    existing_statuses = load_existing_statuses(output_path)

    files_to_process = []
    skipped = 0
    for pdf_path in pdf_files:
        relative_path = pdf_path.relative_to(input_dir).as_posix()
        if should_skip_file(relative_path, existing_statuses, resume, retry_failed):
            skipped += 1
            continue
        files_to_process.append(pdf_path)

    st.info(
        f"Found {len(pdf_files)} PDF file(s). Skipping {skipped}. "
        f"Processing {len(files_to_process)} file(s)."
    )

    if not files_to_process:
        st.success(f"Nothing to process. CSV is available at `{output_path}`.")
        return

    progress = st.progress(0)
    status = st.empty()
    log = st.empty()
    log_lines: list[str] = []
    successes = 0
    failures = 0

    for index, pdf_path in enumerate(files_to_process, start=1):
        relative_path = pdf_path.relative_to(input_dir).as_posix()
        status.text(f"Processing {relative_path} ({index}/{len(files_to_process)})")
        progress.progress((index - 1) / len(files_to_process))

        rows = process_pdf(pdf_path, input_dir, retries, retry_delay_seconds)
        append_rows(output_path, rows)

        if rows[0].get("Status") == "success":
            successes += 1
            log_lines.append(f"OK: {relative_path} ({len(rows)} CSV row(s))")
        else:
            failures += 1
            log_lines.append(f"FAILED: {relative_path} - {rows[0].get('Error')}")

        log.text("\n".join(log_lines[-20:]))
        progress.progress(index / len(files_to_process))

        if delay_seconds > 0:
            time.sleep(delay_seconds)

    status.text("Batch complete")
    st.success(f"Done. Successful files: {successes}. Failed files: {failures}. CSV saved at `{output_path}`.")


def _show_existing_csv(output_path: Path) -> None:
    if not output_path.exists() or output_path.stat().st_size == 0:
        return

    st.markdown("---")
    st.subheader("Current CSV")
    st.caption(str(output_path))

    try:
        df = pd.read_csv(output_path, sep=";", encoding="utf-8-sig")
    except Exception as exc:  # noqa: BLE001
        st.warning(f"Could not preview CSV: {exc}")
        return

    st.metric("CSV rows", len(df))
    st.dataframe(df.tail(200), hide_index=True, width="stretch")
    st.download_button(
        "Download CSV",
        data=output_path.read_bytes(),
        file_name=output_path.name,
        mime="text/csv",
    )


if __name__ == "__main__":
    main()

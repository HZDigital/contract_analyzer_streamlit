"""Batch-process invoice PDFs from a local folder into a CSV file.

This script reuses the API's PDF extraction and Azure OpenAI invoice extraction
logic, but writes each result incrementally so large batches can be resumed
safely.
"""

from __future__ import annotations

import argparse
import csv
import sys
import time
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.utils.ai_analyzer import extract_client_and_products_from_invoices  # noqa: E402
from src.utils.pdf_processor import extract_text_from_pdf  # noqa: E402


CSV_COLUMNS = [
    "Status",
    "Error",
    "Relative Path",
    "File Name",
    "Invoice #",
    "Invoice Date",
    "Due Date",
    "Supplier",
    "Customer",
    "PO #",
    "Product/Service",
    "Description",
    "Quantity",
    "Unit Price",
    "Line Total",
    "Currency",
    "Subtotal",
    "Tax %",
    "Tax Amount",
    "Total Amount",
    "SKU/Part #",
    "Payment Terms",
    "Ship To",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extract invoice information from PDF files in a folder into a CSV file."
    )
    parser.add_argument(
        "--input-dir",
        default=str(REPO_ROOT / "input"),
        help="Folder containing invoice PDFs. Defaults to the repository input/ folder.",
    )
    parser.add_argument(
        "--output",
        default=str(REPO_ROOT / "invoice_results_table.csv"),
        help="CSV file to create or append to. Defaults to invoice_results_table.csv.",
    )
    parser.add_argument(
        "--recursive",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Search subfolders for PDFs. Enabled by default.",
    )
    parser.add_argument(
        "--resume",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Skip files already present in the output CSV. Enabled by default.",
    )
    parser.add_argument(
        "--retry-failed",
        action="store_true",
        help="When resuming, process files again if their previous CSV status was failed.",
    )
    parser.add_argument(
        "--retries",
        type=int,
        default=2,
        help="Number of retries for AI extraction failures. Defaults to 2.",
    )
    parser.add_argument(
        "--retry-delay-seconds",
        type=float,
        default=10.0,
        help="Seconds to wait between retries. Defaults to 10.",
    )
    parser.add_argument(
        "--delay-seconds",
        type=float,
        default=0.0,
        help="Optional delay after each file to reduce API rate pressure. Defaults to 0.",
    )
    return parser.parse_args()


def find_pdf_files(input_dir: Path, recursive: bool) -> list[Path]:
    pattern = "**/*.pdf" if recursive else "*.pdf"
    return sorted(path for path in input_dir.glob(pattern) if path.is_file())


def load_existing_statuses(output_path: Path) -> dict[str, str]:
    if not output_path.exists():
        return {}

    statuses: dict[str, str] = {}
    with output_path.open("r", encoding="utf-8-sig", newline="") as csv_file:
        reader = csv.DictReader(csv_file, delimiter=";")
        for row in reader:
            relative_path = row.get("Relative Path") or row.get("File Name")
            status = row.get("Status", "")
            if relative_path:
                statuses[relative_path] = status
    return statuses


def should_skip_file(
    relative_path: str,
    existing_statuses: dict[str, str],
    resume: bool,
    retry_failed: bool,
) -> bool:
    if not resume or relative_path not in existing_statuses:
        return False

    if retry_failed and existing_statuses[relative_path].lower() == "failed":
        return False

    return True


def ensure_output_file(output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.exists() and output_path.stat().st_size > 0:
        return

    with output_path.open("w", encoding="utf-8-sig", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=CSV_COLUMNS, delimiter=";")
        writer.writeheader()


def append_rows(output_path: Path, rows: list[dict[str, Any]]) -> None:
    with output_path.open("a", encoding="utf-8-sig", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=CSV_COLUMNS, delimiter=";")
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in CSV_COLUMNS})


def build_base_row(
    *,
    status: str,
    error: str,
    pdf_path: Path,
    relative_path: str,
    extracted: dict[str, Any] | None = None,
) -> dict[str, Any]:
    extracted = extracted or {}
    return {
        "Status": status,
        "Error": error,
        "Relative Path": relative_path,
        "File Name": pdf_path.name,
        "Invoice #": extracted.get("invoice_number", "Not specified"),
        "Invoice Date": extracted.get("invoice_date", "Not specified"),
        "Due Date": extracted.get("due_date", "Not specified"),
        "Supplier": extracted.get("supplier_name", extracted.get("company_name", "Not specified")),
        "Customer": extracted.get("customer_name", extracted.get("client_name", "Not specified")),
        "PO #": extracted.get("po_number", "Not specified"),
        "Currency": extracted.get("currency", "Not specified"),
        "Subtotal": extracted.get("subtotal", "Not specified"),
        "Tax %": extracted.get("tax_rate_percent", "Not specified"),
        "Tax Amount": extracted.get("tax_amount", "Not specified"),
        "Total Amount": extracted.get("total_amount", "Not specified"),
        "Payment Terms": extracted.get("payment_terms", "Not specified"),
        "Ship To": extracted.get("ship_to", "Not specified"),
    }


def rows_for_success(pdf_path: Path, relative_path: str, extracted: dict[str, Any]) -> list[dict[str, Any]]:
    products = extracted.get("products") or []
    base_row = build_base_row(
        status="success",
        error=extracted.get("error", ""),
        pdf_path=pdf_path,
        relative_path=relative_path,
        extracted=extracted,
    )

    if not products:
        return [
            {
                **base_row,
                "Product/Service": "No products detected",
                "Description": "-",
                "Quantity": "-",
                "Unit Price": "-",
                "Line Total": "-",
                "SKU/Part #": "-",
            }
        ]

    rows = []
    for product in products:
        rows.append(
            {
                **base_row,
                "Product/Service": product.get("product_name", "Unknown"),
                "Description": product.get("description", "-"),
                "Quantity": f"{product.get('quantity', '-')} {product.get('unit', '')}".strip(),
                "Unit Price": product.get("unit_price", "-"),
                "Line Total": product.get("line_total", "-"),
                "Currency": product.get("currency", extracted.get("currency", "-")),
                "Tax %": product.get("tax_rate_percent", extracted.get("tax_rate_percent", "-")),
                "SKU/Part #": product.get("sku_or_part_number", "-"),
            }
        )
    return rows


def rows_for_failure(pdf_path: Path, relative_path: str, error: str) -> list[dict[str, Any]]:
    return [
        {
            **build_base_row(
                status="failed",
                error=error,
                pdf_path=pdf_path,
                relative_path=relative_path,
            ),
            "Product/Service": "Failed to process",
            "Description": "-",
            "Quantity": "-",
            "Unit Price": "-",
            "Line Total": "-",
            "SKU/Part #": "-",
        }
    ]


def extract_invoice_with_retries(
    text: str,
    retries: int,
    retry_delay_seconds: float,
) -> dict[str, Any]:
    last_result: dict[str, Any] = {}
    attempts = max(retries, 0) + 1

    for attempt in range(1, attempts + 1):
        last_result = extract_client_and_products_from_invoices(text)
        if not last_result.get("error"):
            return last_result

        if attempt < attempts:
            print(
                f"  AI extraction failed: {last_result.get('error')}. "
                f"Retrying in {retry_delay_seconds:g}s..."
            )
            time.sleep(retry_delay_seconds)

    return last_result


def process_pdf(
    pdf_path: Path,
    input_dir: Path,
    retries: int,
    retry_delay_seconds: float,
) -> list[dict[str, Any]]:
    relative_path = pdf_path.relative_to(input_dir).as_posix()

    try:
        with pdf_path.open("rb") as pdf_file:
            text = extract_text_from_pdf(pdf_file)
    except Exception as exc:  # noqa: BLE001
        return rows_for_failure(pdf_path, relative_path, f"PDF read/extraction error: {exc}")

    if not text.strip():
        return rows_for_failure(pdf_path, relative_path, "No text extracted from PDF")

    if text.startswith("[PDF") or text.startswith("[OCR"):
        return rows_for_failure(pdf_path, relative_path, text)

    extracted = extract_invoice_with_retries(text, retries, retry_delay_seconds)
    if extracted.get("error"):
        return rows_for_failure(pdf_path, relative_path, f"AI extraction error: {extracted['error']}")

    return rows_for_success(pdf_path, relative_path, extracted)


def main() -> int:
    args = parse_args()
    input_dir = Path(args.input_dir).expanduser().resolve()
    output_path = Path(args.output).expanduser().resolve()

    if not input_dir.exists() or not input_dir.is_dir():
        print(f"Input folder not found: {input_dir}")
        return 1

    pdf_files = find_pdf_files(input_dir, args.recursive)
    if not pdf_files:
        print(f"No PDF files found in: {input_dir}")
        return 1

    ensure_output_file(output_path)
    existing_statuses = load_existing_statuses(output_path)

    files_to_process = []
    skipped = 0
    for pdf_path in pdf_files:
        relative_path = pdf_path.relative_to(input_dir).as_posix()
        if should_skip_file(relative_path, existing_statuses, args.resume, args.retry_failed):
            skipped += 1
            continue
        files_to_process.append(pdf_path)

    print(f"Input folder: {input_dir}")
    print(f"Output CSV: {output_path}")
    print(f"PDF files found: {len(pdf_files)}")
    print(f"Already in CSV and skipped: {skipped}")
    print(f"Files to process now: {len(files_to_process)}")

    if not files_to_process:
        print("Nothing to process.")
        return 0

    successes = 0
    failures = 0
    for index, pdf_path in enumerate(files_to_process, start=1):
        relative_path = pdf_path.relative_to(input_dir).as_posix()
        print(f"[{index}/{len(files_to_process)}] Processing {relative_path}")

        rows = process_pdf(pdf_path, input_dir, args.retries, args.retry_delay_seconds)
        append_rows(output_path, rows)

        if rows[0].get("Status") == "success":
            successes += 1
            print(f"  Success. Wrote {len(rows)} CSV row(s).")
        else:
            failures += 1
            print(f"  Failed: {rows[0].get('Error')}")

        if args.delay_seconds > 0:
            time.sleep(args.delay_seconds)

    print("Batch complete.")
    print(f"Successful files: {successes}")
    print(f"Failed files: {failures}")
    print(f"CSV saved at: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

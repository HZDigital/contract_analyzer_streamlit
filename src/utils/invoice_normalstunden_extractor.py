"""
Utilities to extract Normalstunden information from invoices using PDF text + AI.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from src.utils.ai_analyzer import extract_client_and_products_from_invoices
from src.utils.pdf_processor import extract_text_from_pdf

MAX_HOURLY_RATE = 1200000000000.0
MIN_HOURLY_RATE = 1.0
SURCHARGE_KEYWORDS = (
    "zuschlag",
    "nacht",
    "sonntag",
    "samstag",
    "feiertag",
    "zulage",
)


def list_pdf_files(input_dir: Path, recursive: bool = True) -> list[Path]:
    """Return PDF files under input_dir, excluding Windows zone identifier artifacts."""
    if recursive:
        files = sorted(input_dir.rglob("*.pdf"))
    else:
        files = sorted(input_dir.glob("*.pdf"))

    return [path for path in files if ":Zone.Identifier" not in path.name]


def extract_normalstunden_from_pdf(pdf_path: Path) -> dict[str, Any]:
    """Extract supplier, hours total, and hourly rate(s) from a single invoice PDF."""
    result = extract_normalstunden_from_bytes(
        pdf_path.read_bytes(),
        pdf_path.name,
        supplier_hint=pdf_path.parent.name,
    )
    result["file_path"] = str(pdf_path)
    return result


def extract_normalstunden_from_bytes(
    pdf_bytes: bytes,
    filename: str,
    supplier_hint: str = "",
) -> dict[str, Any]:
    """Extract Normalstunden from browser-uploaded PDF bytes without filesystem access."""
    text = extract_text_from_pdf(pdf_bytes)
    if not text.strip():
        return {
            "file_name": filename,
            "supplier": supplier_hint,
            "hours_total": None,
            "hourly_rates": [],
            "entries": [],
            "status": "failed",
            "error": "No readable text was found in this invoice.",
        }
    parsed = extract_client_and_products_from_invoices(text)

    if isinstance(parsed, dict) and parsed.get("error"):
        return {
            "file_name": filename,
            "supplier": supplier_hint,
            "hours_total": None,
            "hourly_rates": [],
            "entries": [],
            "status": "failed",
            "error": "This invoice could not be analyzed. Review the source document and try again.",
        }

    supplier = _resolve_supplier(parsed, supplier_hint)
    entries = _extract_ai_normalstunden_entries(parsed)

    if not entries:
        return {
            "file_name": filename,
            "file_path": "",
            "supplier": supplier,
            "supplier_folder": supplier_hint,
            "hours_total": None,
            "hourly_rates": [],
            "hourly_rate_display": "",
            "entries": [],
            "status": "no_match",
            "matched_rows": 0,
        }

    total_hours = round(sum(entry["hours"] for entry in entries), 2)
    unique_rates = sorted({round(entry["hourly_rate"], 2) for entry in entries})
    hourly_rate_display = " | ".join(_format_german_number(rate) for rate in unique_rates)

    return {
        "file_name": filename,
        "file_path": "",
        "supplier": supplier,
        "supplier_folder": supplier_hint,
        "hours_total": total_hours,
        "hourly_rates": unique_rates,
        "hourly_rate_display": hourly_rate_display,
        "entries": [
            {
                "hours": round(entry["hours"], 2),
                "hourly_rate": round(entry["hourly_rate"], 2),
                "hours_display": _format_german_number(entry["hours"]),
                "hourly_rate_display": _format_german_number(entry["hourly_rate"]),
            }
            for entry in entries
        ],
        "status": "success",
        "matched_rows": len(entries),
    }


def _extract_ai_normalstunden_entries(parsed_invoice: dict[str, Any]) -> list[dict[str, float]]:
    """Map AI invoice products into normal-hours entries."""
    products = parsed_invoice.get("products", []) if isinstance(parsed_invoice, dict) else []
    entries: list[dict[str, float]] = []

    for product in products:
        if not isinstance(product, dict):
            continue

        descriptor = " ".join(str(product.get(key, "")) for key in ("product_name", "description")).lower()
        if _contains_surcharge_keyword(descriptor):
            continue

        hours = _parse_number(product.get("quantity"))
        rate = _parse_number(product.get("unit_price"))
        unit = str(product.get("unit", "")).lower().strip()

        unit_looks_hourly = any(token in unit for token in ("std", "stunde", "hour", "h"))
        if unit and not unit_looks_hourly:
            continue

        if hours is None or rate is None:
            continue
        if not (0 < hours <= 350):
            continue
        if not (MIN_HOURLY_RATE <= rate <= MAX_HOURLY_RATE):
            continue

        entries.append({"hours": round(hours, 2), "hourly_rate": round(rate, 2)})

    return entries


def _resolve_supplier(parsed_invoice: dict[str, Any], fallback: str) -> str:
    supplier = ""
    if isinstance(parsed_invoice, dict):
        supplier = str(parsed_invoice.get("supplier_name") or "").strip()
    if not supplier or supplier.lower() == "not specified":
        return fallback
    return supplier


def _contains_surcharge_keyword(text: str) -> bool:
    return any(keyword in text for keyword in SURCHARGE_KEYWORDS)


def _parse_number(value: Any) -> float | None:
    if value is None:
        return None

    text = str(value).strip()
    if not text or text.lower() == "not specified":
        return None

    text = re.sub(r"[^\d,.-]", "", text)
    if not text:
        return None

    if "," in text and "." in text:
        text = text.replace(".", "").replace(",", ".")
    elif "," in text:
        text = text.replace(",", ".")

    try:
        return float(text)
    except ValueError:
        return None


def _format_german_number(value: float) -> str:
    return f"{value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

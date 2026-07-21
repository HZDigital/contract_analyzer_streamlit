from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from typing import Any


ResultRecord = dict[str, Any]
SelectedFields = frozenset[str] | None
Projector = Callable[[Mapping[str, Any], SelectedFields], ResultRecord]
RowProjector = Callable[[Mapping[str, Any]], ResultRecord]
_MISSING = object()
_PUBLIC_ITEM_ERROR = "This item could not be analyzed. Review the source document and try again."
_PRODUCT_GROUPING_WARNING = (
    "Products were extracted, but similar products could not be consolidated. "
    "Review each document result separately."
)
_TENDER_DEFAULT_FIELDS = (
    "customer",
    "project_title",
    "reference_number",
    "procedure",
    "submission_deadline",
    "questions_deadline",
    "contract_start",
    "contract_end",
    "estimated_value",
    "country",
    "language",
    "cpv_codes",
    "notes",
)
_BLOCKED_TENDER_FIELDS = {"chancen in %", "chance in %", "win probability"}


def curate_public_result(
    workflow: str,
    value: Any,
    standard_output_fields: Iterable[str] | None = None,
) -> ResultRecord:
    """Project a workflow result onto its explicit end-user data contract."""

    source = _record(value)
    projector = _PROJECTORS.get(workflow)
    if source is None or projector is None:
        return {"notice": "This analysis result is not available in this application version."}
    selected = frozenset(standard_output_fields) if standard_output_fields is not None else None
    return {"workflow": workflow, **projector(source, selected)}


def _product_request(source: Mapping[str, Any], selected: SelectedFields = None) -> ResultRecord:
    result = {
        "summary": _count_summary(source.get("summary")),
        "results": _documents(source.get("results"), lambda item: _product_document(item, selected)),
    }
    if _included(selected, "consolidated_products"):
        result["consolidated_products"] = _rows(source.get("consolidated_products"), _consolidated_product)
    if source.get("grouping_error") or _nonempty_list(source.get("warnings")):
        result["warnings"] = [_PRODUCT_GROUPING_WARNING]
    return result


def _product_document(source: Mapping[str, Any], selected: SelectedFields = None) -> ResultRecord:
    result = _selected_fields(source, selected, "client_name", "contract_type", "total_estimated_value")
    if _included(selected, "products"):
        result["products"] = _rows(
            source.get("products"),
            lambda item: _fields(item, "product_name", "quantity", "unit", "description"),
        )
    _put_custom_analysis(result, source)
    return result


def _consolidated_product(source: Mapping[str, Any]) -> ResultRecord:
    return {
        **_fields(source, "product"),
        "requests": _rows(
            source.get("requests"),
            lambda item: _fields(item, "client", "original_name", "quantity", "contract_type"),
        ),
    }


def _invoice(source: Mapping[str, Any], selected: SelectedFields = None) -> ResultRecord:
    return {
        "summary": _count_summary(source.get("summary")),
        "results": _documents(source.get("results"), lambda item: _invoice_document(item, selected)),
    }


def _invoice_document(source: Mapping[str, Any], selected: SelectedFields = None) -> ResultRecord:
    result = _selected_fields(
        source,
        selected,
        "invoice_number",
        "invoice_date",
        "due_date",
        "currency",
        "total_amount",
        "subtotal",
        "tax_amount",
        "tax_rate_percent",
        "payment_terms",
        "po_number",
        "contract_type",
        "notes",
    )
    if _included(selected, "supplier"):
        result.update(_fields(source, "supplier_name", "supplier_address", "tax_id"))
    if _included(selected, "customer"):
        result.update(_fields(source, "customer_name", "customer_address", "ship_to"))
    if _included(selected, "products"):
        result["products"] = _rows(
            source.get("products"),
            lambda item: _fields(
                item,
                "product_name",
                "description",
                "quantity",
                "unit",
                "unit_price",
                "line_total",
                "currency",
                "tax_rate_percent",
                "sku_or_part_number",
            ),
        )
    _put_custom_analysis(result, source)
    return result


def _normalstunden(source: Mapping[str, Any], selected: SelectedFields = None) -> ResultRecord:
    return {
        "summary": _count_summary(source.get("summary")),
        "results": _documents(source.get("results"), lambda item: _normalstunden_document(item, selected)),
    }


def _normalstunden_document(source: Mapping[str, Any], selected: SelectedFields = None) -> ResultRecord:
    result = _selected_fields(source, selected, "supplier", "hours_total", "hourly_rates")
    if _included(selected, "entries"):
        result["entries"] = _rows(
            source.get("entries"),
            lambda item: _fields(item, "hours", "hourly_rate"),
        )
    _put_custom_analysis(result, source)
    return result


def _detailed_contract(source: Mapping[str, Any], selected: SelectedFields = None) -> ResultRecord:
    return {
        "summary": _count_summary(source.get("summary")),
        "results": _documents(
            source.get("results"),
            lambda item: _detailed_analysis(item, selected),
            nested_analysis=True,
        ),
    }


def _detailed_analysis(source: Mapping[str, Any], selected: SelectedFields = None) -> ResultRecord:
    result = _selected_fields(source, selected, "summary", "client_name", "contract_type", "start_date", "end_date")
    if _included(selected, "products_services"):
        result["products_services"] = _rows(
            source.get("products_services"),
            lambda item: _fields(item, "name", "description", "quantity", "unit", "rate"),
        )
    if _included(selected, "key_clauses"):
        result["key_clauses"] = _rows(
            source.get("key_clauses"),
            lambda item: _fields(item, "type", "description", "quote"),
        )
    if _included(selected, "risk_areas"):
        result["risk_areas"] = _rows(
            source.get("risk_areas"),
            lambda item: _fields(item, "concern", "quote"),
        )
    _put_custom_analysis(result, source)
    _add_error(result, source)
    return result


def _tender(source: Mapping[str, Any], _selected: SelectedFields = None) -> ResultRecord:
    display_fields = _tender_display_fields(source)
    result = {
        "summary": _count_summary(source.get("summary")),
        "results": _documents(
            source.get("results"),
            lambda item: _tender_analysis(item, display_fields),
            nested_analysis=True,
        ),
        "merged": _tender_merged(source.get("merged"), display_fields),
    }
    _put(result, "template_name", source.get("template_name"))
    return result


def _tender_analysis(source: Mapping[str, Any], display_fields: tuple[str, ...]) -> ResultRecord:
    result = _fields(source, "german_summary", "german_bullets", "key_requirements", "deliverables", "risks", "notes")
    result["extracted"] = _dynamic_fields(source.get("extracted"), display_fields)
    result["tender_fields"] = _dynamic_fields(source.get("tender_fields"), display_fields)
    market = _market_situation(source.get("market_situation"))
    if market:
        result["market_situation"] = market
    _add_error(result, source)
    return result


def _tender_merged(value: Any, display_fields: tuple[str, ...]) -> ResultRecord:
    source = _record(value) or {}
    return {
        "extracted": _dynamic_fields(source.get("extracted"), display_fields),
        "field_sources": _dynamic_fields(source.get("field_sources"), display_fields),
        **_fields(source, "german_summary", "notes"),
    }


def _market_situation(value: Any) -> ResultRecord:
    source = _record(value)
    if source is None:
        return {}
    result = _fields(source, "Vermutliche Wettbewerber", "Letzter Tender", "Split möglich")
    result["sources"] = _rows(
        source.get("sources"),
        lambda item: _fields(item, "title", "url"),
    )
    return result


def _cooperation_review(source: Mapping[str, Any], selected: SelectedFields = None) -> ResultRecord:
    result = _fields(source, "standard_contract", "supplier_agreements")
    analysis = _record(source.get("analysis"))
    result["analysis"] = _cooperation_analysis(analysis or {}, selected)
    _put_custom_analysis(result, source)
    return result


def _cooperation_analysis(source: Mapping[str, Any], selected: SelectedFields = None) -> ResultRecord:
    result: ResultRecord = {}
    if _included(selected, "summary"):
        summary = source.get("summary")
        if isinstance(summary, Mapping):
            result["summary"] = _fields(summary, "contract_type", "parties", "duration", "status", "description")
        else:
            _put(result, "summary", summary)
    if _included(selected, "deviations"):
        result["deviations"] = _rows(
            source.get("deviations"),
            lambda item: _fields(item, "title", "severity", "standard", "supplier", "impact", "section"),
        )
    if _included(selected, "risks"):
        result["risks"] = _rows(
            source.get("risks"),
            lambda item: _fields(
                item,
                "title",
                "category",
                "severity",
                "description",
                "affected_section",
                "quote",
                "recommendation",
            ),
        )
    if _included(selected, "key_clauses"):
        result["key_clauses"] = _rows(
            source.get("key_clauses"),
            lambda item: _fields(item, "type", "description", "quote", "importance"),
        )
    if _included(selected, "recommendations"):
        result["recommendations"] = _rows(
            source.get("recommendations"),
            lambda item: _fields(item, "action", "priority", "rationale", "section"),
        )
    _add_error(result, source)
    return result


def _factory_certificate(source: Mapping[str, Any], selected: SelectedFields = None) -> ResultRecord:
    result = _fields(source, "source_files")
    result["extraction_errors"] = _rows(source.get("extraction_errors"), _failed_source)
    analysis = _record(source.get("analysis"))
    result["analysis"] = _factory_analysis(analysis or {}, selected)
    _put_custom_analysis(result, source)
    return result


def _factory_analysis(source: Mapping[str, Any], selected: SelectedFields = None) -> ResultRecord:
    result = _selected_fields(source, selected, "identified_specs", "identified_certificates", "summary")
    if _included(selected, "comparisons"):
        result["comparisons"] = _rows(
            source.get("comparisons"),
            lambda item: _fields(
                item,
                "parameter",
                "unit",
                "spec_min",
                "spec_max",
                "spec_nominal",
                "measured_value",
                "measured_from",
                "status",
                "deviation",
            ),
        )
    _add_error(result, source)
    return result


def _large_scanner(source: Mapping[str, Any], selected: SelectedFields = None) -> ResultRecord:
    result = _fields(source, "file_name", "page_count")
    if _included(selected, "report"):
        _put(result, "report", source.get("report"))
    merged = _record(source.get("merged"))
    result["merged"] = _large_merged(merged or {}, selected)
    _put_custom_analysis(result, source)
    return result


def _large_merged(source: Mapping[str, Any], selected: SelectedFields = None) -> ResultRecord:
    result = _fields(source, "source_file")
    if _included(selected, "findings_by_category"):
        categories = _record(source.get("findings_by_category")) or {}
        result["findings_by_category"] = {
            str(category): _rows(rows, _large_finding)
            for category, rows in categories.items()
            if str(category).strip() and len(str(category)) <= 160
        }
    if _included(selected, "red_flags"):
        result["red_flags"] = _rows(
            source.get("red_flags"),
            lambda item: _fields(
                item,
                "issue",
                "why_it_matters",
                "section_ref",
                "page_ref",
                "quote",
                "risk_level",
                "inference",
            ),
        )
    if _included(selected, "cross_reference_gaps"):
        result["cross_reference_gaps"] = _rows(
            source.get("cross_reference_gaps"),
            lambda item: _fields(item, "reference", "page_ref", "quote"),
        )
    return result


def _large_finding(source: Mapping[str, Any]) -> ResultRecord:
    return _fields(
        source,
        "category",
        "topic",
        "substance",
        "section_ref",
        "page_ref",
        "quote",
        "inference",
    )


def _put_custom_analysis(target: ResultRecord, source: Mapping[str, Any]) -> None:
    custom = _record(source.get("custom_analysis"))
    if custom is None:
        return
    target["custom_analysis"] = {
        **_fields(custom, "summary", "warning"),
        "findings": _rows(
            custom.get("findings"),
            lambda item: _fields(item, "finding", "explanation", "source_file", "page_ref", "quote"),
        ),
        "fields": _rows(
            custom.get("fields"),
            lambda item: _fields(
                item,
                "field",
                "type",
                "value",
                "explanation",
                "source_file",
                "page_ref",
                "quote",
            ),
        ),
    }


def _documents(value: Any, projector: RowProjector, *, nested_analysis: bool = False) -> list[ResultRecord]:
    documents: list[ResultRecord] = []
    for source in _record_list(value):
        analysis = _record(source.get("analysis")) if nested_analysis else source
        has_error = bool(source.get("error")) or bool(analysis and analysis.get("error"))
        document = _fields(source, "file_name", "status")
        if has_error and document.get("status") == "success":
            document["status"] = "failed"
        _add_error(document, source)
        projected = projector(analysis or {})
        if nested_analysis:
            document["analysis"] = projected
        else:
            document.update(projected)
        documents.append(document)
    return documents


def _failed_source(source: Mapping[str, Any]) -> ResultRecord:
    result = _fields(source, "file_name")
    _add_error(result, source)
    return result


def _count_summary(value: Any) -> ResultRecord:
    source = _record(value)
    if source is None:
        return {}
    result: ResultRecord = {}
    for key in ("total", "successful", "failed", "no_match"):
        item = source.get(key)
        if isinstance(item, int) and not isinstance(item, bool):
            result[key] = item
    return result


def _tender_display_fields(source: Mapping[str, Any]) -> tuple[str, ...]:
    fields = list(_TENDER_DEFAULT_FIELDS)
    configured = source.get("_display_fields")
    if isinstance(configured, (list, tuple)):
        fields.extend(field for field in configured if isinstance(field, str))
    result: list[str] = []
    for field in fields:
        stripped = field.strip()
        if not stripped or stripped.lower() in _BLOCKED_TENDER_FIELDS or stripped in result:
            continue
        result.append(stripped)
    return tuple(result)


def _dynamic_fields(value: Any, allowed: tuple[str, ...]) -> ResultRecord:
    source = _record(value)
    if source is None:
        return {}
    result: ResultRecord = {}
    for field in allowed:
        if field in source:
            _put(result, field, source[field])
    return result


def _fields(source: Mapping[str, Any], *names: str) -> ResultRecord:
    result: ResultRecord = {}
    for name in names:
        if name in source:
            _put(result, name, source[name])
    return result


def _selected_fields(source: Mapping[str, Any], selected: SelectedFields, *names: str) -> ResultRecord:
    return _fields(source, *(name for name in names if _included(selected, name)))


def _included(selected: SelectedFields, field: str) -> bool:
    return selected is None or field in selected


def _put(target: ResultRecord, key: str, value: Any) -> None:
    safe = _safe_value(value)
    if safe is not _MISSING:
        target[key] = safe


def _safe_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (list, tuple)):
        return [item for item in value if item is None or isinstance(item, (str, int, float, bool))]
    return _MISSING


def _add_error(target: ResultRecord, source: Mapping[str, Any]) -> None:
    if source.get("error"):
        target["error"] = _PUBLIC_ITEM_ERROR


def _rows(value: Any, projector: RowProjector) -> list[ResultRecord]:
    return [projector(item) for item in _record_list(value)]


def _record(value: Any) -> Mapping[str, Any] | None:
    return value if isinstance(value, Mapping) else None


def _record_list(value: Any) -> list[Mapping[str, Any]]:
    if not isinstance(value, (list, tuple)):
        return []
    return [item for item in value if isinstance(item, Mapping)]


def _nonempty_list(value: Any) -> bool:
    return isinstance(value, (list, tuple)) and bool(value)


_PROJECTORS: dict[str, Projector] = {
    "product_request": _product_request,
    "invoice": _invoice,
    "normalstunden": _normalstunden,
    "detailed_contract": _detailed_contract,
    "tender": _tender,
    "cooperation_review": _cooperation_review,
    "factory_certificate": _factory_certificate,
    "large_scanner": _large_scanner,
}

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


MAX_CUSTOM_INSTRUCTION_LENGTH = 6_000
MAX_CUSTOM_OUTPUT_FIELDS = 20
MAX_CUSTOM_FIELD_NAME_LENGTH = 80
MAX_CUSTOM_FIELD_INSTRUCTION_LENGTH = 500
CUSTOM_OUTPUT_TYPES = {"text", "number", "yes_no", "list"}
STANDARD_OUTPUT_FIELDS: dict[str, tuple[str, ...]] = {
    "detailed_contract": (
        "summary",
        "client_name",
        "contract_type",
        "start_date",
        "end_date",
        "products_services",
        "key_clauses",
        "risk_areas",
    ),
    "large_scanner": ("report", "findings_by_category", "red_flags", "cross_reference_gaps"),
    "cooperation_review": ("summary", "deviations", "risks", "key_clauses", "recommendations"),
    "product_request": (
        "client_name",
        "contract_type",
        "total_estimated_value",
        "products",
        "consolidated_products",
    ),
    "invoice": (
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
        "supplier",
        "customer",
        "contract_type",
        "notes",
        "products",
    ),
    "normalstunden": ("supplier", "hours_total", "hourly_rates", "entries"),
    "factory_certificate": ("summary", "identified_specs", "identified_certificates", "comparisons"),
}
_CUSTOM_OPTION_KEYS = {
    "customInstructions",
    "custom_instructions",
    "customOutputFields",
    "custom_output_fields",
    "standardOutputFields",
    "standard_output_fields",
}


class CustomizationValidationError(ValueError):
    pass


def normalize_customization_options(options: Mapping[str, Any], workflow: str | None = None) -> dict[str, Any]:
    """Validate and canonicalize the user-editable analysis contract."""

    normalized = {key: value for key, value in options.items() if key not in _CUSTOM_OPTION_KEYS}
    instructions_value = options.get("customInstructions", options.get("custom_instructions", ""))
    if not isinstance(instructions_value, str):
        raise CustomizationValidationError("Custom analysis instructions must be text.")
    instructions = instructions_value.strip()
    if len(instructions) > MAX_CUSTOM_INSTRUCTION_LENGTH:
        raise CustomizationValidationError(
            f"Custom analysis instructions cannot exceed {MAX_CUSTOM_INSTRUCTION_LENGTH:,} characters."
        )

    fields_value = options.get("customOutputFields", options.get("custom_output_fields", []))
    if fields_value is None:
        fields_value = []
    if not isinstance(fields_value, list):
        raise CustomizationValidationError("Custom output fields must be a list.")
    if len(fields_value) > MAX_CUSTOM_OUTPUT_FIELDS:
        raise CustomizationValidationError(
            f"No more than {MAX_CUSTOM_OUTPUT_FIELDS} custom output fields can be requested."
        )

    fields: list[dict[str, str]] = []
    seen_names: set[str] = set()
    for index, value in enumerate(fields_value, 1):
        if not isinstance(value, Mapping):
            raise CustomizationValidationError("Each custom output field must contain a name and output type.")
        name_value = value.get("name", value.get("label", ""))
        instruction_value = value.get("instruction", value.get("description", ""))
        output_type_value = value.get("type", "text")
        if not isinstance(name_value, str) or not name_value.strip():
            raise CustomizationValidationError(f"Custom output field {index} requires a name.")
        if not isinstance(instruction_value, str):
            raise CustomizationValidationError(f"Instructions for custom output field {index} must be text.")
        if not isinstance(output_type_value, str) or output_type_value not in CUSTOM_OUTPUT_TYPES:
            raise CustomizationValidationError(f"Custom output field {index} has an unsupported output type.")

        name = " ".join(name_value.split())
        instruction = instruction_value.strip()
        if len(name) > MAX_CUSTOM_FIELD_NAME_LENGTH:
            raise CustomizationValidationError(
                f"Custom output field names cannot exceed {MAX_CUSTOM_FIELD_NAME_LENGTH} characters."
            )
        if len(instruction) > MAX_CUSTOM_FIELD_INSTRUCTION_LENGTH:
            raise CustomizationValidationError(
                f"Custom output field instructions cannot exceed {MAX_CUSTOM_FIELD_INSTRUCTION_LENGTH} characters."
            )
        comparison_name = name.casefold()
        if comparison_name in seen_names:
            raise CustomizationValidationError(f'Custom output field names must be unique; "{name}" is repeated.')
        seen_names.add(comparison_name)
        fields.append(
            {
                "key": f"field_{index}",
                "name": name,
                "instruction": instruction,
                "type": output_type_value,
            }
        )

    if instructions:
        normalized["customInstructions"] = instructions
    if fields:
        normalized["customOutputFields"] = fields

    standard_fields_present = "standardOutputFields" in options or "standard_output_fields" in options
    if standard_fields_present:
        selected_value = options.get("standardOutputFields", options.get("standard_output_fields"))
        if not isinstance(selected_value, list) or any(not isinstance(item, str) for item in selected_value):
            raise CustomizationValidationError("Standard output fields must be a list of field identifiers.")
        if workflow not in STANDARD_OUTPUT_FIELDS:
            raise CustomizationValidationError("Standard output fields are not configurable for this workflow.")
        allowed = STANDARD_OUTPUT_FIELDS[workflow]
        selected = list(dict.fromkeys(item.strip() for item in selected_value if item.strip()))
        unknown = [item for item in selected if item not in allowed]
        if unknown:
            raise CustomizationValidationError("One or more standard output fields are not supported by this workflow.")
        normalized["standardOutputFields"] = [field for field in allowed if field in selected]
    return normalized


def customization_from_options(options: Mapping[str, Any]) -> dict[str, Any] | None:
    instructions = options.get("customInstructions")
    fields = options.get("customOutputFields")
    if not isinstance(instructions, str):
        instructions = ""
    if not isinstance(fields, list):
        fields = []
    valid_fields = [dict(field) for field in fields if isinstance(field, Mapping)]
    if not instructions and not valid_fields:
        return None
    return {"instructions": instructions, "fields": valid_fields}


def public_customization(options: Mapping[str, Any]) -> dict[str, Any] | None:
    customization = customization_from_options(options)
    standard_fields = options.get("standardOutputFields")
    has_standard_selection = isinstance(standard_fields, list)
    if customization is None and not has_standard_selection:
        return None
    result = {
        "instructions": customization["instructions"] if customization else "",
        "outputFields": [
            {
                "name": str(field.get("name", "")),
                "instruction": str(field.get("instruction", "")),
                "type": str(field.get("type", "text")),
            }
            for field in (customization["fields"] if customization else [])
        ],
    }
    if has_standard_selection:
        result["standardOutputFields"] = [field for field in standard_fields if isinstance(field, str)]
    return result


def standard_output_fields_from_options(workflow: str, options: Mapping[str, Any]) -> tuple[str, ...]:
    """Return the selected public business fields, defaulting old jobs to the full contract."""

    allowed = STANDARD_OUTPUT_FIELDS.get(workflow, ())
    selected = options.get("standardOutputFields")
    if not isinstance(selected, list):
        return allowed
    return tuple(field for field in allowed if field in selected)

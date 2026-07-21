import pytest

from src.api.customization import (
    CustomizationValidationError,
    normalize_customization_options,
    standard_output_fields_from_options,
)


def test_customization_options_are_canonical_and_keep_standard_options() -> None:
    options = normalize_customization_options(
        {
            "includeRiskAssessment": True,
            "custom_instructions": "  Focus on renewal obligations.  ",
            "custom_output_fields": [
                {"name": " Notice period ", "description": "Extract the stated period.", "type": "text"},
                {"name": "Auto renews", "instruction": "Return yes only when explicit.", "type": "yes_no"},
            ],
        }
    )

    assert options == {
        "includeRiskAssessment": True,
        "customInstructions": "Focus on renewal obligations.",
        "customOutputFields": [
            {
                "key": "field_1",
                "name": "Notice period",
                "instruction": "Extract the stated period.",
                "type": "text",
            },
            {
                "key": "field_2",
                "name": "Auto renews",
                "instruction": "Return yes only when explicit.",
                "type": "yes_no",
            },
        ],
    }


def test_customization_rejects_duplicate_names_case_insensitively() -> None:
    with pytest.raises(CustomizationValidationError, match="must be unique"):
        normalize_customization_options(
            {
                "customOutputFields": [
                    {"name": "Notice period", "type": "text"},
                    {"name": "notice PERIOD", "type": "number"},
                ]
            }
        )


def test_customization_enforces_instruction_and_field_count_limits() -> None:
    accepted = normalize_customization_options(
        {
            "customInstructions": "x" * 6_000,
            "customOutputFields": [
                {"name": f"Field {index}", "type": "text"}
                for index in range(20)
            ],
        }
    )
    assert len(accepted["customOutputFields"]) == 20

    with pytest.raises(CustomizationValidationError, match="6,000"):
        normalize_customization_options({"customInstructions": "x" * 6_001})
    with pytest.raises(CustomizationValidationError, match="No more than 20"):
        normalize_customization_options(
            {
                "customOutputFields": [
                    {"name": f"Field {index}", "type": "text"}
                    for index in range(21)
                ]
            }
        )


def test_standard_output_selection_is_validated_and_preserves_canonical_order() -> None:
    options = normalize_customization_options(
        {"standard_output_fields": ["risk_areas", "summary", "risk_areas"]},
        "detailed_contract",
    )

    assert options["standardOutputFields"] == ["summary", "risk_areas"]
    assert standard_output_fields_from_options("detailed_contract", options) == ("summary", "risk_areas")
    assert "client_name" in standard_output_fields_from_options("detailed_contract", {})

    with pytest.raises(CustomizationValidationError, match="not supported"):
        normalize_customization_options(
            {"standardOutputFields": ["summary", "provider_debug"]},
            "detailed_contract",
        )


def test_empty_standard_output_selection_is_preserved() -> None:
    options = normalize_customization_options({"standardOutputFields": []}, "invoice")

    assert options["standardOutputFields"] == []
    assert standard_output_fields_from_options("invoice", options) == ()

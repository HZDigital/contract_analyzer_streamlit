from types import SimpleNamespace

from src.utils.custom_analysis import analyze_custom_output, merge_custom_outputs


class _FakeCompletions:
    def __init__(self, content: str) -> None:
        self.content = content
        self.messages = None
        self.kwargs = None

    def create(self, **kwargs):
        self.kwargs = kwargs
        self.messages = kwargs["messages"]
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=self.content))]
        )


def test_custom_analysis_balances_sources_and_keeps_only_verified_evidence(monkeypatch) -> None:
    completions = _FakeCompletions(
        """
        {
          "summary": "Review complete",
          "findings": [
            {
              "finding": "A renewal clause exists.",
              "explanation": "Review before expiry.",
              "source_file": "supplier.pdf",
              "page_ref": "Page 99",
              "quote": "This quotation was invented."
            }
          ],
          "fields": [
            {
              "key": "field_1",
              "value": "30 days",
              "explanation": "Stated payment term.",
              "source_file": "supplier.pdf",
              "page_ref": "Page 2",
              "quote": "Payment is due in 30 days."
            },
            {
              "key": "field_2",
              "value": true,
              "explanation": "The payment clause is explicit.",
              "source_file": "supplier.pdf",
              "page_ref": "Page 1",
              "quote": "Payment is due in 30 days."
            }
          ]
        }
        """
    )
    monkeypatch.setattr(
        "src.utils.custom_analysis.azure_config",
        SimpleNamespace(
            client=SimpleNamespace(chat=SimpleNamespace(completions=completions)),
            deployment_name="test-model",
        ),
    )

    result = analyze_custom_output(
        {
            "instructions": "Focus on payment and renewal.",
            "fields": [
                {"key": "field_1", "name": "Payment period", "type": "text", "instruction": ""},
                {"key": "field_2", "name": "Payment stated", "type": "yes_no", "instruction": ""},
            ],
        },
        source_texts={
            "standard.pdf": "[Page 1]\n" + "Standard terms. " * 3_000,
            "supplier.pdf": "[Page 2]\nPayment is due in 30 days. " + "Supplier terms. " * 3_000,
        },
        page_aware=True,
    )

    assert result is not None
    assert result["fields"][0]["quote"] == "Payment is due in 30 days."
    assert result["fields"][0]["page_ref"] == "Page 2"
    assert result["fields"][1]["value"] is True
    assert result["fields"][1]["quote"] == "Payment is due in 30 days."
    assert result["fields"][1]["page_ref"] == ""
    assert result["findings"] == []
    prompt = completions.messages[1]["content"]
    assert "=== SOURCE: standard.pdf ===" in prompt
    assert "=== SOURCE: supplier.pdf ===" in prompt
    assert "Focus on payment and renewal." not in completions.messages[0]["content"]
    assert "temperature" not in completions.kwargs


def test_empty_customization_does_not_access_the_model() -> None:
    assert analyze_custom_output(None, source_texts={"contract.pdf": "Contract"}) is None
    assert analyze_custom_output({"instructions": "", "fields": []}, source_texts={"contract.pdf": "Contract"}) is None


def test_invalid_typed_value_clears_unverified_field_metadata(monkeypatch) -> None:
    completions = _FakeCompletions(
        """
        {
          "summary": "",
          "findings": [],
          "fields": [{
            "key": "field_1",
            "value": "not a number",
            "explanation": "Unsupported assertion",
            "source_file": "contract.pdf",
            "page_ref": "Page 1",
            "quote": "The amount is 25."
          }]
        }
        """
    )
    monkeypatch.setattr(
        "src.utils.custom_analysis.azure_config",
        SimpleNamespace(
            client=SimpleNamespace(chat=SimpleNamespace(completions=completions)),
            deployment_name="test-model",
        ),
    )

    result = analyze_custom_output(
        {
            "instructions": "",
            "fields": [{"key": "field_1", "name": "Amount", "type": "number", "instruction": ""}],
        },
        source_texts={"contract.pdf": "[Page 1]\nThe amount is 25."},
        page_aware=True,
    )

    assert result is not None
    assert result["fields"][0] == {
        "key": "field_1",
        "field": "Amount",
        "type": "number",
        "value": None,
        "explanation": "",
        "source_file": "",
        "page_ref": "",
        "quote": "",
    }


def test_labelled_page_range_with_to_binds_quote_to_all_pages(monkeypatch) -> None:
    completions = _FakeCompletions(
        """
        {
          "summary": "",
          "findings": [],
          "fields": [{
            "key": "field_1",
            "value": "30 days",
            "explanation": "Found on the second page in the range.",
            "source_file": "contract.pdf",
            "page_ref": "Pages 2 to 3",
            "quote": "Payment is due in 30 days."
          }]
        }
        """
    )
    monkeypatch.setattr(
        "src.utils.custom_analysis.azure_config",
        SimpleNamespace(
            client=SimpleNamespace(chat=SimpleNamespace(completions=completions)),
            deployment_name="test-model",
        ),
    )

    result = analyze_custom_output(
        {
            "instructions": "",
            "fields": [{"key": "field_1", "name": "Payment", "type": "text", "instruction": ""}],
        },
        source_texts={
            "contract.pdf": "[Page 2]\nIntroduction.\n[Page 3]\nPayment is due in 30 days."
        },
        page_aware=True,
    )

    assert result is not None
    assert result["fields"][0]["page_ref"] == "Pages 2 to 3"


def test_deep_output_merge_preserves_every_requested_field_before_extra_values() -> None:
    outputs = [
        {
            "summary": "",
            "findings": [],
            "fields": [
                {
                    "key": f"field_{field}",
                    "field": f"Field {field}",
                    "type": "text",
                    "value": f"value-{chunk}-{field}",
                    "source_file": "contract.pdf",
                    "quote": f"quote-{chunk}-{field}",
                }
                for field in range(1, 21)
            ],
        }
        for chunk in range(5)
    ]

    merged = merge_custom_outputs(outputs)

    assert merged is not None
    assert len(merged["fields"]) == 80
    assert {field["key"] for field in merged["fields"]} == {
        f"field_{field}" for field in range(1, 21)
    }

import json

from src.api.workflows import WorkflowInput, run_workflow


def test_detailed_contract_reports_an_unreadable_pdf(monkeypatch) -> None:
    monkeypatch.setattr(
        "src.api.workflows.extract_text_from_pdf",
        lambda _data: (_ for _ in ()).throw(ValueError("The PDF could not be opened.")),
    )

    result = run_workflow(
        {"workflow": "detailed_contract", "options": {}},
        [WorkflowInput(name="contract.pdf", role="contracts", data=b"not-a-pdf")],
    )

    document = result.result["results"][0]
    assert document["status"] == "failed"
    assert document["error"] == "The PDF could not be opened."


def test_detailed_contract_marks_analyzer_failures_as_failed(monkeypatch) -> None:
    monkeypatch.setattr("src.api.workflows.extract_text_from_pdf", lambda _data: "A contract")
    monkeypatch.setattr(
        "src.api.workflows.analyze_contract", lambda _text, _length: {"error": "configuration_missing"}
    )

    result = run_workflow(
        {"workflow": "detailed_contract", "options": {}},
        [WorkflowInput(name="contract.pdf", role="contracts", data=b"pdf")],
    )

    document = result.result["results"][0]
    assert document["status"] == "failed"
    assert document["error"] == "The analysis service is not configured."


def test_detailed_contract_always_uses_maximum_standard_review_coverage(monkeypatch) -> None:
    observed: dict[str, int] = {}
    monkeypatch.setattr("src.api.workflows.extract_text_from_pdf", lambda _data: "x" * 40_000)

    def analyze(_text: str, truncate_length: int) -> dict[str, str]:
        observed["truncate_length"] = truncate_length
        return {"summary": "Reviewed"}

    monkeypatch.setattr("src.api.workflows.analyze_contract", analyze)

    result = run_workflow(
        {"workflow": "detailed_contract", "options": {"truncateLength": 1_000}},
        [WorkflowInput(name="contract.pdf", role="contracts", data=b"pdf")],
    )

    assert result.result["results"][0]["status"] == "success"
    assert observed["truncate_length"] == 30_000


def test_invoice_marks_analyzer_error_payload_as_failed_without_raw_details(monkeypatch) -> None:
    monkeypatch.setattr("src.api.workflows.extract_text_from_pdf", lambda _data: "An invoice")
    monkeypatch.setattr(
        "src.api.workflows.extract_client_and_products_from_invoices",
        lambda _text: {"error": "HTTPSConnectionPool(host=internal.example, request_id=secret)"},
    )

    result = run_workflow(
        {"workflow": "invoice", "options": {}},
        [WorkflowInput(name="invoice.pdf", role="invoices", data=b"pdf")],
    )

    document = result.result["results"][0]
    assert document["status"] == "failed"
    assert document["error"] == "The analysis service could not process this document. Please try again."
    assert "internal.example" not in str(result.result)


def test_product_grouping_failure_keeps_results_with_a_stable_warning(monkeypatch) -> None:
    monkeypatch.setattr("src.api.workflows.extract_text_from_pdf", lambda _data: "A request")
    monkeypatch.setattr(
        "src.api.workflows.extract_client_and_products",
        lambda _text: {
            "client_name": "Example GmbH",
            "products": [{"product_name": "Steel", "quantity": "10", "unit": "kg"}],
            "contract_type": "Request",
        },
    )
    monkeypatch.setattr(
        "src.api.workflows.group_similar_products",
        lambda _products: {"error": "internal model endpoint", "groups": []},
    )

    result = run_workflow(
        {"workflow": "product_request", "options": {"groupSimilarProducts": True}},
        [WorkflowInput(name="request.pdf", role="requests", data=b"pdf")],
    )

    assert result.result["summary"] == {"total": 1, "successful": 1, "failed": 0}
    assert result.result["warnings"] == [
        "Products were extracted, but similar products could not be consolidated. Review each document result separately."
    ]
    assert "internal model endpoint" not in str(result.result)


def test_detailed_contract_attaches_additive_custom_output(monkeypatch) -> None:
    monkeypatch.setattr("src.api.workflows.extract_text_from_pdf", lambda _data: "Thirty days' notice is required.")
    monkeypatch.setattr("src.api.workflows.analyze_contract", lambda _text, _length: {"summary": "Standard review"})
    monkeypatch.setattr(
        "src.api.workflows.analyze_custom_output",
        lambda customization, *, source_texts, page_aware=False: {
            "summary": customization["instructions"],
            "findings": [],
            "fields": [
                {
                    "field": customization["fields"][0]["name"],
                    "type": "text",
                    "value": "30 days",
                    "source_file": next(iter(source_texts)),
                    "quote": "Thirty days' notice is required.",
                }
            ],
        },
    )

    result = run_workflow(
        {
            "workflow": "detailed_contract",
            "options": {
                "customInstructions": "Extract termination requirements.",
                "customOutputFields": [
                    {"key": "field_1", "name": "Notice period", "instruction": "", "type": "text"}
                ],
            },
        },
        [WorkflowInput(name="contract.pdf", role="contracts", data=b"pdf")],
    )

    custom = result.result["results"][0]["analysis"]["custom_analysis"]
    assert custom["summary"] == "Extract termination requirements."
    assert custom["fields"][0]["field"] == "Notice period"


def test_removed_standard_fields_do_not_reappear_in_standard_review_exports(monkeypatch) -> None:
    monkeypatch.setattr("src.api.workflows.extract_text_from_pdf", lambda _data: "Contract text")
    monkeypatch.setattr(
        "src.api.workflows.analyze_contract",
        lambda _text, _length: {
            "summary": "Hidden summary",
            "client_name": "Hidden customer",
            "risk_areas": [{"concern": "Retained risk", "quote": "Contract text"}],
        },
    )

    result = run_workflow(
        {"workflow": "detailed_contract", "options": {"standardOutputFields": ["risk_areas"]}},
        [WorkflowInput(name="contract.pdf", role="contracts", data=b"pdf")],
    )

    analysis = result.result["results"][0]["analysis"]
    assert analysis == {"risk_areas": [{"concern": "Retained risk", "quote": "Contract text"}]}
    csv_text = next(artifact.data for artifact in result.artifacts if artifact.name.endswith(".csv")).decode("utf-8-sig")
    markdown = next(artifact.data for artifact in result.artifacts if artifact.name.endswith(".md")).decode()
    csv_header = csv_text.splitlines()[0].split(";")
    assert "summary" not in csv_header
    assert "client_name" not in csv_header
    assert "risk_areas" in csv_header
    assert "### Summary" not in markdown
    assert "### Client Name" not in markdown
    assert "### Risk Areas" in markdown
    assert "Hidden summary" not in csv_text + markdown
    assert "Hidden customer" not in csv_text + markdown
    assert "Retained risk" in csv_text + markdown


def test_product_and_normalstunden_exports_use_only_selected_standard_columns(monkeypatch) -> None:
    monkeypatch.setattr("src.api.workflows.extract_text_from_pdf", lambda _data: "Source text")
    monkeypatch.setattr(
        "src.api.workflows.extract_client_and_products",
        lambda _text: {
            "client_name": "Hidden customer",
            "contract_type": "Hidden type",
            "total_estimated_value": "42,000 EUR",
            "products": [{"product_name": "Hidden product"}],
        },
    )
    product_result = run_workflow(
        {
            "workflow": "product_request",
            "options": {
                "groupSimilarProducts": False,
                "standardOutputFields": ["total_estimated_value"],
            },
        },
        [WorkflowInput(name="request.pdf", role="requests", data=b"pdf")],
    )
    product_csv = next(
        artifact.data for artifact in product_result.artifacts if artifact.name.endswith(".csv")
    ).decode("utf-8-sig")
    product_header = product_csv.splitlines()[0].split(";")
    assert "total_estimated_value" in product_header
    assert "client_name" not in product_header
    assert "contract_type" not in product_header
    assert "product_name" not in product_header

    monkeypatch.setattr(
        "src.api.workflows.extract_normalstunden_from_text",
        lambda _text, filename, _hint: {
            "file_name": filename,
            "status": "success",
            "supplier": "Hidden supplier",
            "hours_total": 10,
            "hourly_rates": [100],
            "entries": [{"hours": 10, "hourly_rate": 100}],
        },
    )
    hours_result = run_workflow(
        {"workflow": "normalstunden", "options": {"standardOutputFields": []}},
        [WorkflowInput(name="invoice.pdf", role="normalstundenPdfs", data=b"pdf")],
    )
    hours_csv = next(
        artifact.data for artifact in hours_result.artifacts if artifact.name.endswith(".csv")
    ).decode("utf-8-sig")
    hours_header = hours_csv.splitlines()[0].split(";")
    assert hours_header == ["file_name", "status"]


def test_deep_review_keeps_private_qa_context_but_removes_it_from_evidence_export(monkeypatch) -> None:
    monkeypatch.setattr(
        "src.api.workflows.extract_pdf_pages",
        lambda _data: [{"page": 1, "text": "Payment is due in 30 days.", "extraction_method": "native"}],
    )
    monkeypatch.setattr(
        "src.api.workflows.build_contract_chunks",
        lambda _pages, **_kwargs: [{"chunk_id": "chunk-1", "text": "[Page 1]\nPayment is due in 30 days."}],
    )
    monkeypatch.setattr("src.api.workflows.analyze_contract_chunks", lambda _chunks, progress_callback: [{}])
    monkeypatch.setattr(
        "src.api.workflows.merge_chunk_findings",
        lambda _results, _chunks: {"source_file": "contract.pdf", "findings_by_category": {}},
    )
    monkeypatch.setattr("src.api.workflows.synthesize_contract_analysis", lambda _merged, **_kwargs: "Report")

    result = run_workflow(
        {"workflow": "large_scanner", "options": {"standardOutputFields": []}},
        [WorkflowInput(name="contract.pdf", role="contract", data=b"pdf")],
    )

    assert "qa_context" in result.result
    evidence = next(artifact for artifact in result.artifacts if artifact.name.endswith("evidence.json"))
    assert "qa_context" not in json.loads(evidence.data)
    assert all(not artifact.name.endswith("report.md") for artifact in result.artifacts)

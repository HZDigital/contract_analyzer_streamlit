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

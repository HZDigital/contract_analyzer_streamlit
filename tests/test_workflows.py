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

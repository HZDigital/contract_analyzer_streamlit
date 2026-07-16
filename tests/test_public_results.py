from src.api.public_results import curate_public_result


def test_curated_result_keeps_business_fields_and_removes_internal_fields() -> None:
    result = curate_public_result(
        "large_scanner",
        {
            "workflow": "large_scanner",
            "report": "Business review",
            "qa_context": {"chunks": [{"text": "private contract text"}]},
            "chunk_results": [{"error": "provider endpoint and request ID"}],
            "settings": {"max_chars": 18000},
            "merged": {
                "findings_by_category": {
                    "Commercial Terms": [
                        {
                            "topic": "Payment",
                            "substance": "Payment is due in 30 days.",
                            "page_ref": "Page 4",
                            "quote": "Payment is due within 30 days.",
                            "chunk_id": "chunk_0001",
                            "confidence": "high",
                            "unexpected_model_field": "must not be public",
                        }
                    ]
                },
                "errors": [{"error": "raw provider failure"}],
                "standard_topics": ["internal taxonomy"],
            },
        },
    )

    assert result["report"] == "Business review"
    finding = result["merged"]["findings_by_category"]["Commercial Terms"][0]
    assert finding == {
        "topic": "Payment",
        "substance": "Payment is due in 30 days.",
        "page_ref": "Page 4",
        "quote": "Payment is due within 30 days.",
    }
    assert "private contract text" not in str(result)
    assert "provider" not in str(result)


def test_curated_result_sanitizes_errors_and_dynamic_tender_fields() -> None:
    result = curate_public_result(
        "tender",
        {
            "workflow": "tender",
            "_display_fields": ["Submission deadline", "settings", "error", "Chancen in %"],
            "results": [
                {
                    "file_name": "tender.pdf",
                    "status": "failed",
                    "error": "HTTPSConnectionPool(host=internal.example)",
                }
            ],
            "merged": {
                "extracted": {
                    "Submission deadline": "2026-09-10",
                    "settings": "A trusted template value",
                    "error": "A second trusted template value",
                    "Chancen in %": "82%",
                }
            },
        },
    )

    assert result["results"][0]["error"] == (
        "This item could not be analyzed. Review the source document and try again."
    )
    assert result["merged"]["extracted"] == {
        "Submission deadline": "2026-09-10",
        "settings": "A trusted template value",
        "error": "A second trusted template value",
    }


def test_valid_field_names_are_rejected_in_unexpected_locations() -> None:
    result = curate_public_result(
        "factory_certificate",
        {
            "workflow": "factory_certificate",
            "source_files": ["certificate.pdf"],
            "analysis": {
                "summary": "Review complete",
                "source_files": ["model-invented.pdf"],
                "template_name": "internal.xlsx",
            },
        },
    )

    assert result["source_files"] == ["certificate.pdf"]
    assert result["analysis"] == {
        "summary": "Review complete",
        "comparisons": [],
    }


def test_unknown_workflow_never_exposes_arbitrary_result_data() -> None:
    result = curate_public_result("future_workflow", {"debug": "private", "value": 42})

    assert result == {"notice": "This analysis result is not available in this application version."}

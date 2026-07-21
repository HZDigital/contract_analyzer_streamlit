from src.api.schemas import FileRole, InputReference, JobArtifact, JobRecord, JobSource, MAX_PROGRESS_LOG_ENTRIES


def test_job_public_payload_hides_owner_and_blob_locations() -> None:
    job = JobRecord(
        owner_oid="user-object-id",
        workflow="invoice",
        status="completed",
        file_roles=[FileRole(role="invoices", name="invoice.pdf")],
        input_refs=[
            InputReference(
                name="invoice.pdf",
                role="invoices",
                content_type="application/pdf",
                size=42,
                blob_name="owners/private/jobs/id/inputs/file.pdf",
            )
        ],
        artifacts=[
            JobArtifact(
                id="artifact-id",
                name="invoice.csv",
                content_type="text/csv",
                size=12,
                blob_name="owners/private/jobs/id/artifacts/file.csv",
            )
        ],
        sources=[
            JobSource(
                id="source-id",
                name="invoice.pdf",
                role="invoices",
                content_type="application/pdf",
                size=42,
                blob_name="owners/private/jobs/id/sources/source.pdf",
            )
        ],
        result={
            "workflow": "invoice",
            "results": [{"file_name": "invoice.pdf", "status": "success", "invoice_number": "INV-42", "debug": "private"}],
        },
        error="HTTPSConnectionPool(host=internal.example, request_id=secret)",
    )

    public = job.public()

    assert public["artifacts"] == [
        {"id": "artifact-id", "name": "invoice.csv", "contentType": "text/csv", "size": 12}
    ]
    assert public["sources"] == [
        {
            "id": "source-id",
            "name": "invoice.pdf",
            "role": "invoices",
            "contentType": "application/pdf",
            "size": 42,
            "previewable": True,
        }
    ]
    assert "ownerOid" not in public
    assert "inputRefs" not in public
    assert "blobName" not in str(public)
    assert public["result"]["results"][0]["invoice_number"] == "INV-42"
    assert "debug" not in str(public)
    assert public["error"] == "Analysis could not be completed. Review the source documents and try again."
    assert "internal.example" not in str(public)

    summary = job.summary_public()
    assert set(summary) == {"id", "workflow", "status", "createdAt", "updatedAt", "progress", "files"}
    assert "result" not in summary
    assert "sources" not in summary
    assert "artifacts" not in summary

    tender = JobRecord(
        owner_oid="owner-1",
        workflow="tender",
        status="completed",
        result={
            "workflow": "tender",
            "_display_fields": ["Custom template field"],
            "merged": {"extracted": {"Custom template field": "Required", "debug": "private"}},
        },
    ).public()
    assert tender["result"]["merged"]["extracted"] == {"Custom template field": "Required"}
    assert "_display_fields" not in str(tender)


def test_running_job_hides_checkpointed_sources() -> None:
    job = JobRecord(
        owner_oid="user-object-id",
        workflow="invoice",
        status="running",
        sources=[
            JobSource(
                id="source-id",
                name="invoice.pdf",
                role="invoices",
                content_type="application/pdf",
                size=42,
                blob_name="owners/private/jobs/id/sources/source.pdf",
            )
        ],
        artifacts=[
            JobArtifact(
                id="artifact-id",
                name="invoice.csv",
                content_type="text/csv",
                size=12,
                blob_name="owners/private/jobs/id/artifacts/file.csv",
            )
        ],
        result={"supplier": "Private checkpoint"},
        finalization_ready=True,
    )

    public = job.public()

    assert public["sources"] == []
    assert public["artifacts"] == []
    assert public["result"] is None
    assert "finalizationReady" not in public


def test_job_progress_log_is_bounded_and_only_returned_from_job_detail() -> None:
    job = JobRecord(owner_oid="user-object-id", workflow="invoice")
    job.record_progress(0, "Queued")
    job.record_progress(12, "Extracting invoice.pdf")
    job.record_progress(12, "Extracting invoice.pdf")
    job.record_progress(7, "Processing invoice.pdf")
    job.record_progress(100, "Analysis complete")

    public = job.public()

    assert public["progressLog"] == [
        {"at": event.at.isoformat(), "progress": event.progress, "message": event.message}
        for event in job.progress_log
    ]
    assert [event["progress"] for event in public["progressLog"]] == [0, 12, 12, 100]
    assert "progressLog" not in job.summary_public()

    for index in range(MAX_PROGRESS_LOG_ENTRIES + 1):
        job.record_progress(100, f"Finalizing step {index}")

    assert len(job.progress_log) == MAX_PROGRESS_LOG_ENTRIES
    assert job.progress_log[0].message == "Finalizing step 1"


def test_job_public_payload_describes_customization_without_internal_field_keys() -> None:
    job = JobRecord(
        owner_oid="user-object-id",
        workflow="invoice",
        options={
            "customInstructions": "Focus on payment controls.",
            "customOutputFields": [
                {
                    "key": "field_1",
                    "name": "Approval required",
                    "instruction": "Return yes only when explicit.",
                    "type": "yes_no",
                }
            ],
        },
    )

    public = job.public()

    assert public["customization"] == {
        "instructions": "Focus on payment controls.",
        "outputFields": [
            {
                "name": "Approval required",
                "instruction": "Return yes only when explicit.",
                "type": "yes_no",
            }
        ],
    }
    assert "field_1" not in str(public["customization"])


def test_job_public_payload_applies_selected_standard_output_fields() -> None:
    job = JobRecord(
        owner_oid="user-object-id",
        workflow="invoice",
        status="completed",
        options={"standardOutputFields": ["invoice_number", "supplier"]},
        result={
            "summary": {"total": 1, "successful": 1, "failed": 0},
            "results": [
                {
                    "file_name": "invoice.pdf",
                    "status": "success",
                    "invoice_number": "INV-42",
                    "total_amount": "120.00",
                    "supplier_name": "Supplier GmbH",
                }
            ],
        },
    )

    public = job.public()

    assert public["customization"]["standardOutputFields"] == ["invoice_number", "supplier"]
    assert public["result"]["results"][0] == {
        "file_name": "invoice.pdf",
        "status": "success",
        "invoice_number": "INV-42",
        "supplier_name": "Supplier GmbH",
    }

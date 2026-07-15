from src.api.schemas import FileRole, InputReference, JobArtifact, JobRecord


def test_job_public_payload_hides_owner_and_blob_locations() -> None:
    job = JobRecord(
        owner_oid="user-object-id",
        workflow="invoice",
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
    )

    public = job.public()

    assert public["artifacts"] == [
        {"id": "artifact-id", "name": "invoice.csv", "contentType": "text/csv", "size": 12}
    ]
    assert "ownerOid" not in public
    assert "inputRefs" not in public
    assert "blobName" not in str(public)

from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

from src.api.jobs import JobDispatcher, JobService, _retained_source_uploads
from src.api.schemas import InputReference, JobRecord
from src.api.settings import Settings


class _FailingCleanupStorage:
    def delete_inputs(self, _job: JobRecord) -> None:
        raise RuntimeError("temporary Blob failure")


def test_terminal_input_cleanup_is_best_effort() -> None:
    settings = Settings()
    dispatcher = JobDispatcher(JobService(_FailingCleanupStorage(), settings))  # type: ignore[arg-type]

    dispatcher._delete_inputs_best_effort(JobRecord(owner_oid="object-id", workflow="invoice"))


def test_normalstunden_archive_members_are_retained_as_previewable_sources() -> None:
    output = BytesIO()
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        archive.writestr("supplier-a/invoice.pdf", b"pdf")
    archive_data = output.getvalue()
    job = JobRecord(
        owner_oid="object-id",
        workflow="normalstunden",
        options={"includeSubfolders": True},
    )
    reference = InputReference(
        name="invoices.zip",
        role="normalstundenArchive",
        content_type="application/zip",
        size=len(archive_data),
        blob_name="private/input.zip",
    )

    retained = _retained_source_uploads(job, [(reference, archive_data)], Settings())

    assert [(source.name, source.role) for source in retained] == [
        ("invoices.zip", "normalstundenArchive"),
        ("invoice.pdf", "normalstundenArchivePdf"),
    ]


def test_normalstunden_retained_sources_honor_string_subfolder_option() -> None:
    output = BytesIO()
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        archive.writestr("root.pdf", b"root")
        archive.writestr("supplier-a/nested.pdf", b"nested")
    archive_data = output.getvalue()
    job = JobRecord(
        owner_oid="object-id",
        workflow="normalstunden",
        options={"includeSubfolders": "false"},
    )
    reference = InputReference(
        name="invoices.zip",
        role="normalstundenArchive",
        content_type="application/zip",
        size=len(archive_data),
        blob_name="private/input.zip",
    )

    retained = _retained_source_uploads(job, [(reference, archive_data)], Settings())

    assert [source.name for source in retained] == ["invoices.zip", "root.pdf"]

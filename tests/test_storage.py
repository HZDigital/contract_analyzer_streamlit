from typing import Any

from src.api.schemas import JobRecord
from src.api.settings import Settings
from src.api import storage as storage_module
from src.api.storage import BlobJobStorage


def test_manifest_uses_the_same_retention_tag_as_its_result_data() -> None:
    storage = BlobJobStorage(Settings.model_validate({"AZURE_STORAGE_CONNECTION_STRING": "UseDevelopmentStorage=true"}))
    captured: dict[str, Any] = {}

    def capture_write(*_args: Any, **kwargs: Any) -> None:
        captured.update(kwargs)

    storage._write_bytes = capture_write  # type: ignore[method-assign]
    storage.save_job(JobRecord(owner_oid="object-id", workflow="invoice", retention="temporary"), create_only=True)

    assert captured["tags"] == {"kind": "manifest", "retention": "temporary"}


def test_source_uses_an_opaque_path_and_starts_transient() -> None:
    storage = BlobJobStorage(Settings.model_validate({"AZURE_STORAGE_CONNECTION_STRING": "UseDevelopmentStorage=true"}))
    captured: dict[str, Any] = {}

    def capture_write(name: str, *_args: Any, **kwargs: Any) -> None:
        captured["name"] = name
        captured.update(kwargs)

    storage._write_bytes = capture_write  # type: ignore[method-assign]
    job = JobRecord(owner_oid="object-id", workflow="invoice", retention="temporary")

    source = storage.save_source(job, name="invoice.pdf", role="invoices", data=b"pdf")

    assert source.name == "invoice.pdf"
    assert source.content_type == "application/pdf"
    assert captured["name"].endswith(f"/sources/{source.id}.pdf")
    assert captured["tags"] == {"kind": "source", "retention": "transient"}


def test_artifact_starts_transient_until_the_private_checkpoint_is_published() -> None:
    storage = BlobJobStorage(Settings.model_validate({"AZURE_STORAGE_CONNECTION_STRING": "UseDevelopmentStorage=true"}))
    captured: dict[str, Any] = {}

    def capture_write(name: str, *_args: Any, **kwargs: Any) -> None:
        captured["name"] = name
        captured.update(kwargs)

    storage._write_bytes = capture_write  # type: ignore[method-assign]
    job = JobRecord(owner_oid="object-id", workflow="invoice", retention="permanent")

    artifact = storage.save_artifact(job, name="invoice.csv", content_type="text/csv", data=b"result")

    assert captured["name"].endswith(f"/artifacts/{artifact.id}.csv")
    assert captured["tags"] == {"kind": "artifact", "retention": "transient"}


def test_acquired_manifest_lease_uses_the_sdk_lease_id(monkeypatch) -> None:
    class FakeLease:
        def __init__(self, _blob: object) -> None:
            self.id = "proposed-lease-id"

        def acquire(self, **_kwargs: Any) -> None:
            self.id = "server-assigned-lease-id"

    storage = BlobJobStorage(Settings.model_validate({"AZURE_STORAGE_CONNECTION_STRING": "UseDevelopmentStorage=true"}))
    monkeypatch.setattr(storage_module, "BlobLeaseClient", FakeLease)
    monkeypatch.setattr(storage, "ensure_container", lambda: None)
    monkeypatch.setattr(storage, "_blob_client", lambda _name: object())

    lease = storage.acquire_job_lease("object-id", "00000000-0000-0000-0000-000000000001")

    assert lease is not None
    assert lease.lease_id == "server-assigned-lease-id"

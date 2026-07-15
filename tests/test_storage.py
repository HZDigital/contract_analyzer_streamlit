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

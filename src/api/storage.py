"""Blob-backed storage for private analyzer jobs and artifacts."""

from __future__ import annotations

import base64
import hashlib
import json
import threading
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Iterable
from uuid import UUID, uuid4, uuid5

from azure.core.exceptions import ResourceExistsError, ResourceNotFoundError
from azure.identity import DefaultAzureCredential
from azure.storage.blob import BlobLeaseClient, BlobServiceClient, ContentSettings

from .schemas import InputReference, JobArtifact, JobRecord, JobSource, utc_now
from .settings import Settings
from .uploads import ValidatedUpload


class StorageNotConfiguredError(RuntimeError):
    """Raised when an API operation needs Blob Storage but it is unavailable."""


class JobNotFoundError(LookupError):
    """Raised when an owner does not have the requested job."""


_SOURCE_CONTENT_TYPES = {
    ".doc": "application/msword",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".pdf": "application/pdf",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".zip": "application/zip",
}


@dataclass
class JobLease:
    """An acquired manifest lease used to serialize work across replicas."""

    client: BlobLeaseClient
    lease_id: str


class BlobJobStorage:
    """Stores every durable job resource in a private owner/job Blob prefix."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._service: BlobServiceClient | None = None
        self._container_ready = False
        self._container_lock = threading.Lock()

    def _service_client(self) -> BlobServiceClient:
        if self._service is not None:
            return self._service
        if not self.settings.storage_configured:
            raise StorageNotConfiguredError("Blob job storage is not configured.")
        if self.settings.azure_storage_connection_string:
            self._service = BlobServiceClient.from_connection_string(self.settings.azure_storage_connection_string)
        else:
            credential = DefaultAzureCredential(exclude_interactive_browser_credential=True)
            self._service = BlobServiceClient(
                account_url=str(self.settings.azure_storage_account_url),
                credential=credential,
            )
        return self._service

    def _container_client(self):
        return self._service_client().get_container_client(self.settings.azure_storage_container_name)

    def ensure_container(self) -> None:
        """Create the configured private container for local development if needed."""

        if self._container_ready:
            return
        with self._container_lock:
            if self._container_ready:
                return
            container = self._container_client()
            try:
                container.get_container_properties()
            except ResourceNotFoundError:
                try:
                    container.create_container()
                except ResourceExistsError:
                    pass
            self._container_ready = True

    @staticmethod
    def _owner_key(owner_oid: str) -> str:
        # Do not expose Entra object IDs in Blob paths or operational diagnostics.
        return hashlib.sha256(owner_oid.encode("utf-8")).hexdigest()

    @staticmethod
    def _validated_job_id(job_id: str) -> str:
        try:
            return str(UUID(job_id))
        except (ValueError, TypeError) as exc:
            raise JobNotFoundError("Job not found.") from exc

    def _job_prefix(self, owner_oid: str, job_id: str) -> str:
        return f"owners/{self._owner_key(owner_oid)}/jobs/{self._validated_job_id(job_id)}"

    def _manifest_name(self, owner_oid: str, job_id: str) -> str:
        return f"{self._job_prefix(owner_oid, job_id)}/manifest.json"

    def _blob_client(self, name: str):
        return self._container_client().get_blob_client(name)

    def _write_bytes(
        self,
        name: str,
        data: bytes,
        content_type: str,
        *,
        overwrite: bool = True,
        tags: dict[str, str] | None = None,
        lease_id: str | None = None,
    ) -> None:
        self.ensure_container()
        self._blob_client(name).upload_blob(
            data,
            overwrite=overwrite,
            lease=lease_id,
            tags=tags,
            content_settings=ContentSettings(content_type=content_type),
        )

    def _read_bytes(self, name: str) -> bytes:
        self.ensure_container()
        try:
            return self._blob_client(name).download_blob().readall()
        except ResourceNotFoundError as exc:
            raise JobNotFoundError("Job not found.") from exc

    def create_job(self, job: JobRecord, uploads: Iterable[ValidatedUpload]) -> JobRecord:
        """Write source inputs first, then publish the manifest for worker discovery."""

        self.ensure_container()
        prefix = self._job_prefix(job.owner_oid, job.id)
        references: list[InputReference] = []
        try:
            for upload in uploads:
                suffix = PurePosixPath(upload.name).suffix.lower()
                blob_name = f"{prefix}/inputs/{uuid4().hex}{suffix}"
                self._write_bytes(
                    blob_name,
                    upload.data,
                    upload.content_type or "application/octet-stream",
                    overwrite=False,
                    tags={"kind": "input", "retention": "transient"},
                )
                references.append(
                    InputReference(
                        name=upload.name,
                        role=upload.role,
                        content_type=upload.content_type,
                        size=len(upload.data),
                        blob_name=blob_name,
                        supplier_hint=upload.supplier_hint,
                    )
                )
            job.input_refs = references
            job.files = [reference.name for reference in references]
            self.save_job(job, create_only=True)
            return job
        except Exception:
            self.delete_prefix(job.owner_oid, job.id, ignore_missing=True)
            raise

    def save_job(self, job: JobRecord, *, lease_id: str | None = None, create_only: bool = False) -> None:
        job.updated_at = job.updated_at if create_only else utc_now()
        payload = json.dumps(job.model_dump(by_alias=True, mode="json"), ensure_ascii=False).encode("utf-8")
        self._write_bytes(
            self._manifest_name(job.owner_oid, job.id),
            payload,
            "application/json",
            overwrite=not create_only,
            # Results are stored in this manifest as well as downloadable artifacts,
            # so it must be included in the lifecycle policy.
            tags={"kind": "manifest", "retention": job.retention},
            lease_id=lease_id,
        )

    def get_job(self, owner_oid: str, job_id: str) -> JobRecord:
        try:
            data = json.loads(self._read_bytes(self._manifest_name(owner_oid, job_id)))
            job = JobRecord.model_validate(data)
        except (json.JSONDecodeError, ValueError) as exc:
            raise JobNotFoundError("Job not found.") from exc
        if job.owner_oid != owner_oid:
            raise JobNotFoundError("Job not found.")
        return job

    def list_jobs(self, owner_oid: str) -> list[JobRecord]:
        self.ensure_container()
        prefix = f"owners/{self._owner_key(owner_oid)}/jobs/"
        jobs: list[JobRecord] = []
        for blob in self._container_client().list_blobs(name_starts_with=prefix):
            if not blob.name.endswith("/manifest.json"):
                continue
            try:
                jobs.append(JobRecord.model_validate(json.loads(self._read_bytes(blob.name))))
            except (JobNotFoundError, ValueError, json.JSONDecodeError):
                continue
        return sorted((job for job in jobs if job.owner_oid == owner_oid), key=lambda job: job.updated_at, reverse=True)

    def list_pending_jobs(self) -> list[JobRecord]:
        """Return manifests eligible for a lease claim; callers decide staleness."""

        self.ensure_container()
        jobs: list[JobRecord] = []
        for blob in self._container_client().list_blobs(name_starts_with="owners/"):
            if not blob.name.endswith("/manifest.json"):
                continue
            try:
                jobs.append(JobRecord.model_validate(json.loads(self._read_bytes(blob.name))))
            except (JobNotFoundError, ValueError, json.JSONDecodeError):
                continue
        return jobs

    def acquire_job_lease(self, owner_oid: str, job_id: str) -> JobLease | None:
        self.ensure_container()
        blob = self._blob_client(self._manifest_name(owner_oid, job_id))
        lease = BlobLeaseClient(blob)
        try:
            lease.acquire(lease_duration=self.settings.job_lease_seconds)
            return JobLease(client=lease, lease_id=lease.id)
        except (ResourceNotFoundError, ResourceExistsError):
            return None

    @staticmethod
    def renew_lease(lease: JobLease) -> None:
        lease.client.renew()

    @staticmethod
    def release_lease(lease: JobLease) -> None:
        try:
            lease.client.release()
        except ResourceNotFoundError:
            pass

    def load_inputs(self, job: JobRecord) -> list[tuple[InputReference, bytes]]:
        return [(reference, self._read_bytes(reference.blob_name)) for reference in job.input_refs]

    def delete_inputs(self, job: JobRecord) -> None:
        for reference in job.input_refs:
            try:
                self._blob_client(reference.blob_name).delete_blob()
            except ResourceNotFoundError:
                continue

    def save_artifact(
        self,
        job: JobRecord,
        *,
        name: str,
        content_type: str,
        data: bytes,
        artifact_id: str | None = None,
    ) -> JobArtifact:
        artifact_id = artifact_id or str(uuid4())
        suffix = PurePosixPath(name).suffix.lower()
        blob_name = f"{self._job_prefix(job.owner_oid, job.id)}/artifacts/{artifact_id}{suffix}"
        self._write_bytes(
            blob_name,
            data,
            content_type,
            overwrite=True,
            tags={"kind": "artifact", "retention": "transient"},
        )
        return JobArtifact(
            id=artifact_id,
            name=PurePosixPath(name).name,
            content_type=content_type,
            size=len(data),
            blob_name=blob_name,
        )

    @staticmethod
    def artifact_id(job: JobRecord, index: int, name: str) -> str:
        """Return a stable artifact ID so finalization can be replayed safely."""

        return str(uuid5(UUID(job.id), f"{index}:{PurePosixPath(name).name}"))

    def save_outcome(self, job: JobRecord, result: dict, artifacts: Iterable[object]) -> None:
        """Checkpoint a complete in-memory workflow outcome for crash recovery."""

        payload = {
            "result": result,
            "artifacts": [
                {
                    "name": str(getattr(artifact, "name")),
                    "contentType": str(getattr(artifact, "content_type")),
                    "data": base64.b64encode(bytes(getattr(artifact, "data"))).decode("ascii"),
                }
                for artifact in artifacts
            ],
        }
        self._write_bytes(
            f"{self._job_prefix(job.owner_oid, job.id)}/outcome.json",
            json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            "application/json",
            tags={"kind": "outcome", "retention": "transient"},
        )

    def load_outcome(self, job: JobRecord):
        """Load a private workflow checkpoint without re-running analysis."""

        from .workflows import WorkflowArtifact, WorkflowResult

        try:
            payload = json.loads(
                self._read_bytes(f"{self._job_prefix(job.owner_oid, job.id)}/outcome.json")
            )
            result = payload["result"]
            artifacts = [
                WorkflowArtifact(
                    data=base64.b64decode(item["data"], validate=True),
                    name=item["name"],
                    content_type=item["contentType"],
                )
                for item in payload["artifacts"]
            ]
            if not isinstance(result, dict):
                raise ValueError("Workflow result must be an object.")
            return WorkflowResult(result=result, artifacts=artifacts)
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise JobNotFoundError("Workflow outcome unavailable.") from exc

    def delete_outcome(self, job: JobRecord) -> None:
        try:
            self._blob_client(f"{self._job_prefix(job.owner_oid, job.id)}/outcome.json").delete_blob()
        except ResourceNotFoundError:
            pass

    def save_source(
        self,
        job: JobRecord,
        *,
        name: str,
        role: str,
        data: bytes,
    ) -> JobSource:
        source_id = str(uuid4())
        safe_name = PurePosixPath(name).name
        suffix = PurePosixPath(safe_name).suffix.lower()
        content_type = _SOURCE_CONTENT_TYPES.get(suffix, "application/octet-stream")
        blob_name = f"{self._job_prefix(job.owner_oid, job.id)}/sources/{source_id}{suffix}"
        self._write_bytes(
            blob_name,
            data,
            content_type,
            overwrite=False,
            # Sources remain short-lived until a running manifest checkpoints
            # their IDs. This prevents a terminated worker from orphaning a
            # permanent source that no manifest can authorize or delete.
            tags={"kind": "source", "retention": "transient"},
        )
        return JobSource(
            id=source_id,
            name=safe_name,
            role=role,
            content_type=content_type,
            size=len(data),
            blob_name=blob_name,
        )

    def promote_sources(self, job: JobRecord, sources: Iterable[JobSource]) -> None:
        """Move checkpointed sources onto the job's selected retention."""

        self.ensure_container()
        for source in sources:
            client = self._blob_client(source.blob_name)
            try:
                # Updating metadata resets lifecycle age to finalization time;
                # Set Blob Tags alone does not change Last-Modified.
                client.set_blob_metadata({})
                client.set_blob_tags({"kind": "source", "retention": job.retention})
            except ResourceNotFoundError as exc:
                raise JobNotFoundError("Staged source unavailable.") from exc

    def promote_artifacts(self, job: JobRecord, artifacts: Iterable[JobArtifact]) -> None:
        """Move checkpointed exports onto the job's selected retention."""

        self.ensure_container()
        for artifact in artifacts:
            try:
                client = self._blob_client(artifact.blob_name)
                client.set_blob_metadata({})
                client.set_blob_tags({"kind": "artifact", "retention": job.retention})
            except ResourceNotFoundError as exc:
                raise JobNotFoundError("Staged artifact unavailable.") from exc

    def promote_context(self, job: JobRecord) -> None:
        """Move checkpointed analysis context onto the job's selected retention."""

        self.ensure_container()
        try:
            client = self._blob_client(f"{self._job_prefix(job.owner_oid, job.id)}/context.json")
            client.set_blob_metadata({})
            client.set_blob_tags({"kind": "context", "retention": job.retention})
        except ResourceNotFoundError as exc:
            raise JobNotFoundError("Staged analysis context unavailable.") from exc

    def delete_sources(self, sources: Iterable[JobSource]) -> None:
        first_error: Exception | None = None
        for source in sources:
            try:
                # If deletion is temporarily unavailable, the lifecycle rule
                # must still be able to collect an unpublished source.
                self._blob_client(source.blob_name).set_blob_tags(
                    {"kind": "source", "retention": "transient"}
                )
                self._blob_client(source.blob_name).delete_blob()
            except ResourceNotFoundError:
                continue
            except Exception as exc:  # noqa: BLE001
                first_error = first_error or exc
        if first_error is not None:
            raise first_error

    def delete_artifacts(self, artifacts: Iterable[JobArtifact]) -> None:
        first_error: Exception | None = None
        for artifact in artifacts:
            try:
                self._blob_client(artifact.blob_name).set_blob_tags(
                    {"kind": "artifact", "retention": "transient"}
                )
                self._blob_client(artifact.blob_name).delete_blob()
            except ResourceNotFoundError:
                continue
            except Exception as exc:  # noqa: BLE001
                first_error = first_error or exc
        if first_error is not None:
            raise first_error

    def delete_context(self, job: JobRecord) -> None:
        client = self._blob_client(f"{self._job_prefix(job.owner_oid, job.id)}/context.json")
        try:
            client.set_blob_tags({"kind": "context", "retention": "transient"})
            client.delete_blob()
        except ResourceNotFoundError:
            pass

    def save_context(self, job: JobRecord, data: bytes) -> None:
        self._write_bytes(
            f"{self._job_prefix(job.owner_oid, job.id)}/context.json",
            data,
            "application/json",
            tags={"kind": "context", "retention": "transient"},
        )

    def load_context(self, job: JobRecord) -> dict:
        try:
            value = json.loads(self._read_bytes(f"{self._job_prefix(job.owner_oid, job.id)}/context.json"))
        except (json.JSONDecodeError, ValueError) as exc:
            raise JobNotFoundError("Analysis context is unavailable.") from exc
        if not isinstance(value, dict):
            raise JobNotFoundError("Analysis context is unavailable.")
        return value

    def load_artifact(self, job: JobRecord, artifact_id: str) -> tuple[JobArtifact, bytes]:
        artifact = next((item for item in job.artifacts if item.id == artifact_id), None)
        if artifact is None:
            raise JobNotFoundError("Artifact not found.")
        return artifact, self._read_bytes(artifact.blob_name)

    def load_source(self, job: JobRecord, source_id: str) -> tuple[JobSource, bytes]:
        source = next((item for item in job.sources if item.id == source_id), None)
        if source is None:
            raise JobNotFoundError("Source not found.")
        return source, self._read_bytes(source.blob_name)

    def delete_prefix(self, owner_oid: str, job_id: str, *, ignore_missing: bool = False) -> None:
        self.ensure_container()
        prefix = f"{self._job_prefix(owner_oid, job_id)}/"
        for blob in self._container_client().list_blobs(name_starts_with=prefix):
            try:
                self._container_client().delete_blob(blob.name)
            except ResourceNotFoundError:
                if not ignore_missing:
                    raise

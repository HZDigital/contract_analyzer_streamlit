"""Blob-lease job orchestration and background dispatch."""

from __future__ import annotations

import asyncio
import json
import logging
import threading
from collections.abc import Callable
from datetime import timedelta
from typing import Any

from fastapi import HTTPException, status

from src.utils.large_contract_analyzer import answer_contract_question

from .schemas import CurrentUser, FileRole, JobRecord, utc_now
from .settings import Settings
from .storage import BlobJobStorage, JobLease, JobNotFoundError, StorageNotConfiguredError
from .uploads import ValidatedUpload
from .workflows import WorkflowInput, run_workflow


logger = logging.getLogger(__name__)


class JobService:
    """Owner-scoped API operations over durable job manifests."""

    def __init__(self, storage: BlobJobStorage, settings: Settings) -> None:
        self.storage = storage
        self.settings = settings

    def _require_storage(self) -> None:
        if not self.settings.storage_configured:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Job storage is not configured.")

    def create_job(
        self,
        user: CurrentUser,
        workflow: str,
        retention: str,
        retention_days: int | None,
        options: dict[str, Any],
        uploads: list[ValidatedUpload],
    ) -> JobRecord:
        self._require_storage()
        if retention not in {"temporary", "permanent"}:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Retention must be temporary or permanent.")
        if retention == "temporary":
            # Temporary artifacts use the lifecycle policy's fixed 60-day expiry.
            retention_days = 60
        else:
            retention_days = None
        job = JobRecord(
            owner_oid=user.oid,
            workflow=workflow,
            retention=retention,
            retention_days=retention_days,
            files=[upload.name for upload in uploads],
            file_roles=[FileRole(role=upload.role, name=upload.name) for upload in uploads],
            options=options,
        )
        try:
            return self.storage.create_job(job, uploads)
        except StorageNotConfiguredError as exc:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Job storage is not configured.") from exc

    def get_job(self, user: CurrentUser, job_id: str) -> JobRecord:
        self._require_storage()
        try:
            return self.storage.get_job(user.oid, job_id)
        except JobNotFoundError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found.") from exc
        except StorageNotConfiguredError as exc:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Job storage is not configured.") from exc

    def list_jobs(self, user: CurrentUser) -> list[JobRecord]:
        self._require_storage()
        try:
            return self.storage.list_jobs(user.oid)
        except StorageNotConfiguredError as exc:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Job storage is not configured.") from exc

    def delete_job(self, user: CurrentUser, job_id: str) -> None:
        job = self.get_job(user, job_id)
        if job.status in {"queued", "running"}:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A running job cannot be deleted.")
        try:
            self.storage.delete_prefix(user.oid, job.id)
        except StorageNotConfiguredError as exc:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Job storage is not configured.") from exc

    def get_artifact(self, user: CurrentUser, job_id: str, artifact_id: str):
        job = self.get_job(user, job_id)
        try:
            return self.storage.load_artifact(job, artifact_id)
        except JobNotFoundError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Artifact not found.") from exc

    def answer_question(self, user: CurrentUser, job_id: str, question: str) -> str:
        job = self.get_job(user, job_id)
        if job.workflow != "large_scanner" or job.status != "completed":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Questions are available after a large scan completes.")
        try:
            context = self.storage.load_context(job)
        except JobNotFoundError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Analysis context is unavailable.") from exc
        chunks = context.get("chunks")
        merged = context.get("merged")
        if not isinstance(chunks, list) or not isinstance(merged, dict):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Analysis context is unavailable.")
        return answer_contract_question(question, chunks, merged)


class _LeaseHeartbeat:
    """Keeps the finite Azure Blob lease alive through long OCR and LLM calls."""

    def __init__(self, storage: BlobJobStorage, lease: JobLease, lease_seconds: int) -> None:
        self.storage = storage
        self.lease = lease
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="contract-analyzer-lease", daemon=True)
        self._interval = max(5, lease_seconds // 2)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread.ident is not None:
            self._thread.join(timeout=self._interval + 2)

    def _run(self) -> None:
        while not self._stop.wait(self._interval):
            try:
                self.storage.renew_lease(self.lease)
            except Exception:  # noqa: BLE001
                # The worker's next manifest save will fail safely if ownership is lost.
                logger.warning("Analyzer job lease renewal failed")
                return


class JobDispatcher:
    """Scans Blob manifests and processes leased jobs without a separate queue service."""

    def __init__(self, service: JobService) -> None:
        self.service = service
        self.storage = service.storage
        self.settings = service.settings
        self._task: asyncio.Task[None] | None = None
        self._stop = asyncio.Event()
        self._active: set[str] = set()
        self._workers: set[asyncio.Task[None]] = set()
        self._semaphore = asyncio.Semaphore(self.settings.job_concurrency)

    async def start(self) -> None:
        if self.settings.storage_configured:
            self._task = asyncio.create_task(self._loop(), name="contract-analyzer-job-dispatcher")

    async def stop(self) -> None:
        self._stop.set()
        if self._task is not None:
            await self._task
        if self._workers:
            await asyncio.gather(*self._workers, return_exceptions=True)

    async def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                await self.run_once()
            except Exception:  # noqa: BLE001
                logger.exception("Analyzer job dispatcher cycle failed")
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self.settings.job_poll_seconds)
            except TimeoutError:
                continue

    async def run_once(self) -> None:
        candidates = await asyncio.to_thread(self.storage.list_pending_jobs)
        now = utc_now()
        for job in candidates:
            is_stale = job.status == "running" and now - job.updated_at > timedelta(seconds=self.settings.job_recovery_seconds)
            if job.status != "queued" and not is_stale:
                continue
            if job.id in self._active:
                continue
            self._active.add(job.id)
            worker = asyncio.create_task(self._run_with_slot(job.id, job.owner_oid), name=f"contract-analyzer-job-{job.id}")
            self._workers.add(worker)
            worker.add_done_callback(self._workers.discard)

    async def _run_with_slot(self, job_id: str, owner_oid: str) -> None:
        try:
            async with self._semaphore:
                await asyncio.to_thread(self._run_job, owner_oid, job_id)
        except Exception:  # noqa: BLE001
            logger.exception("Analyzer worker crashed before completing job: %s", job_id)
        finally:
            self._active.discard(job_id)

    def _run_job(self, owner_oid: str, job_id: str) -> None:
        lease = self.storage.acquire_job_lease(owner_oid, job_id)
        if lease is None:
            return
        heartbeat = _LeaseHeartbeat(self.storage, lease, self.settings.job_lease_seconds)
        try:
            job = self.storage.get_job(owner_oid, job_id)
            now = utc_now()
            if job.status == "running" and now - job.updated_at <= timedelta(seconds=self.settings.job_recovery_seconds):
                return
            if job.status not in {"queued", "running"}:
                return

            job.status = "running"
            job.started_at = job.started_at or now
            job.progress = max(job.progress, 1)
            job.message = "Preparing analysis"
            job.error = None
            job.attempt += 1
            self.storage.save_job(job, lease_id=lease.lease_id)
            heartbeat.start()

            def update_progress(progress: int, message: str) -> None:
                job.progress = max(job.progress, min(99, int(progress)))
                job.message = message[:240]
                self.storage.save_job(job, lease_id=lease.lease_id)

            input_files = [
                WorkflowInput(reference.name, reference.role, data, reference.content_type, reference.supplier_hint)
                for reference, data in self.storage.load_inputs(job)
            ]
            outcome = run_workflow(job, input_files, update_progress)
            result = dict(outcome.result)
            context = result.pop("qa_context", None)
            if isinstance(context, dict):
                self.storage.save_context(
                    job,
                    json.dumps(context, ensure_ascii=False).encode("utf-8"),
                )
            job.artifacts = [
                self.storage.save_artifact(
                    job,
                    name=artifact.name,
                    content_type=artifact.content_type,
                    data=artifact.data,
                )
                for artifact in outcome.artifacts
            ]
            job.result = result
            job.status = "completed"
            job.progress = 100
            job.message = "Analysis complete"
            job.completed_at = utc_now()
            self.storage.save_job(job, lease_id=lease.lease_id)
            # Publish the terminal state before deleting inputs. If the manifest
            # write loses its lease, recovery still has the original documents.
            self._delete_inputs_best_effort(job)
            logger.info("Analyzer job completed: %s", job.id)
        except Exception:  # noqa: BLE001
            logger.exception("Analyzer job failed: %s", job_id)
            try:
                job = self.storage.get_job(owner_oid, job_id)
                job.status = "failed"
                job.error = "Analysis failed. Check the inputs and try again."
                job.message = "Analysis failed"
                job.completed_at = utc_now()
                self.storage.save_job(job, lease_id=lease.lease_id)
                self._delete_inputs_best_effort(job)
            except Exception:  # noqa: BLE001
                logger.exception("Unable to persist analyzer job failure: %s", job_id)
        finally:
            heartbeat.stop()
            self.storage.release_lease(lease)

    def _delete_inputs_best_effort(self, job: JobRecord) -> None:
        """Terminal manifests are authoritative; lifecycle cleanup covers retry failures."""

        try:
            self.storage.delete_inputs(job)
        except Exception:  # noqa: BLE001
            logger.warning("Unable to remove analyzer job inputs: %s", job.id)

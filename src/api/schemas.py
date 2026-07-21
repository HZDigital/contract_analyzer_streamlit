"""API and durable job models."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Literal, Optional
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from src.api.customization import public_customization, standard_output_fields_from_options
from src.api.public_results import curate_public_result


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


MAX_PROGRESS_LOG_ENTRIES = 100


class CurrentUser(BaseModel):
    oid: str
    subject: str
    tenant_id: str
    name: Optional[str] = None
    preferred_username: Optional[str] = None


class FileRole(BaseModel):
    role: str
    name: str


class InputReference(BaseModel):
    name: str
    role: str
    content_type: Optional[str] = None
    size: int
    blob_name: str
    supplier_hint: str = ""


class JobArtifact(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    name: str
    content_type: str = Field(alias="contentType")
    size: int
    blob_name: str = Field(alias="blobName")

    def public(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "contentType": self.content_type,
            "size": self.size,
        }


class JobSource(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    name: str
    role: str
    content_type: str = Field(alias="contentType")
    size: int
    blob_name: str = Field(alias="blobName")

    def public(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "role": self.role,
            "contentType": self.content_type,
            "size": self.size,
            "previewable": self.content_type == "application/pdf",
        }


class JobProgressEvent(BaseModel):
    at: datetime = Field(default_factory=utc_now)
    progress: int = Field(ge=0, le=100)
    message: str = Field(min_length=1, max_length=240)

    def public(self) -> dict[str, Any]:
        return {
            "at": self.at.isoformat(),
            "progress": self.progress,
            "message": self.message,
        }


class JobRecord(BaseModel):
    """Durable manifest. Input/blob locations are never returned to the browser."""

    model_config = ConfigDict(populate_by_name=True)

    id: str = Field(default_factory=lambda: str(uuid4()))
    owner_oid: str = Field(alias="ownerOid")
    workflow: str
    retention: Literal["temporary", "permanent"] = "temporary"
    retention_days: Optional[int] = Field(default=60, alias="retentionDays")
    status: Literal["queued", "running", "completed", "failed", "cancelled"] = "queued"
    progress: int = Field(default=0, ge=0, le=100)
    message: str = "Queued"
    progress_log: list[JobProgressEvent] = Field(default_factory=list, alias="progressLog")
    error: Optional[str] = None
    created_at: datetime = Field(default_factory=utc_now, alias="createdAt")
    updated_at: datetime = Field(default_factory=utc_now, alias="updatedAt")
    started_at: Optional[datetime] = Field(default=None, alias="startedAt")
    completed_at: Optional[datetime] = Field(default=None, alias="completedAt")
    files: list[str] = Field(default_factory=list)
    file_roles: list[FileRole] = Field(default_factory=list, alias="fileRoles")
    input_refs: list[InputReference] = Field(default_factory=list, alias="inputRefs")
    options: dict[str, Any] = Field(default_factory=dict)
    result: Optional[Any] = None
    artifacts: list[JobArtifact] = Field(default_factory=list)
    sources: list[JobSource] = Field(default_factory=list)
    context_staged: bool = Field(default=False, alias="contextStaged")
    finalization_ready: bool = Field(default=False, alias="finalizationReady")
    attempt: int = 0

    def record_progress(self, progress: int, message: str) -> None:
        """Update the public status and retain a bounded, curated activity history."""

        self.progress = max(self.progress, min(100, int(progress)))
        self.message = message.strip()[:240] or "Updating analysis"
        if self.progress_log and (
            self.progress_log[-1].progress == self.progress and self.progress_log[-1].message == self.message
        ):
            return
        self.progress_log.append(JobProgressEvent(progress=self.progress, message=self.message))
        if len(self.progress_log) > MAX_PROGRESS_LOG_ENTRIES:
            del self.progress_log[:-MAX_PROGRESS_LOG_ENTRIES]

    def summary_public(self) -> dict[str, Any]:
        """Small list payload without completed analysis content or download selectors."""

        return {
            "id": self.id,
            "workflow": self.workflow,
            "status": self.status,
            "createdAt": self.created_at.isoformat(),
            "updatedAt": self.updated_at.isoformat(),
            "progress": self.progress,
            "files": self.files,
        }

    def public(self) -> dict[str, Any]:
        completed = self.status == "completed"
        expires_at = (
            self.completed_at + timedelta(days=self.retention_days or 60)
            if completed and self.retention == "temporary" and self.completed_at
            else None
        )
        return {
            "id": self.id,
            "workflow": self.workflow,
            "status": self.status,
            "createdAt": self.created_at.isoformat(),
            "updatedAt": self.updated_at.isoformat(),
            "startedAt": self.started_at.isoformat() if self.started_at else None,
            "completedAt": self.completed_at.isoformat() if self.completed_at else None,
            "progress": self.progress,
            "message": self.message,
            "progressLog": [event.public() for event in self.progress_log],
            "error": (
                "Analysis could not be completed. Review the source documents and try again."
                if self.error
                else None
            ),
            "files": self.files,
            "retention": self.retention,
            "retentionDays": self.retention_days,
            "expiresAt": expires_at.isoformat() if expires_at else None,
            "coverage": self._coverage_notes(),
            "customization": public_customization(self.options),
            "artifacts": [artifact.public() for artifact in self.artifacts] if completed else [],
            # Running manifests can contain a private finalization checkpoint.
            "sources": [source.public() for source in self.sources] if completed else [],
            "result": (
                curate_public_result(
                    self.workflow,
                    self.result,
                    standard_output_fields_from_options(self.workflow, self.options),
                )
                if completed
                else None
            ),
        }

    def _coverage_notes(self) -> list[str]:
        notes: list[str] = []
        if self.workflow == "detailed_contract":
            # Older manifests may not contain the explicit limit stored on new jobs.
            default_limit = 12000 if str(self.options.get("analysisDepth", "standard")).lower() == "thorough" else 3500
            limit = _bounded_option(self.options, "truncateLength", "truncate_length", default=default_limit, low=1000, high=30000)
            notes.append(f"Standard review examines up to the first {limit:,} characters of each document.")
            notes.append("Use Deep review when clauses or schedules may appear later in a long document.")
        elif self.workflow == "large_scanner":
            page_count = self.result.get("page_count") if isinstance(self.result, dict) else None
            if isinstance(page_count, int):
                notes.append(f"Deep review analyzed {page_count:,} readable PDF pages in overlapping sections.")
            else:
                notes.append("Deep review analyzes readable PDF pages in overlapping sections.")
            complete = _bool_option(self.options, "isCompleteDocument", "is_complete_document", default=True)
            notes.append(
                "The upload was declared to be the complete document."
                if complete
                else "The upload was declared to contain only part of the document."
            )
        elif self.workflow == "cooperation_review":
            limit = _bounded_option(self.options, "truncateLength", "truncate_length", default=12000, low=1000, high=30000)
            notes.append(
                f"The comparison examines up to {limit:,} characters from the combined supplier agreements and the standard contract."
            )
            if len(self.files) > 2:
                notes.append("Supplier agreements are analyzed together; verify which source supports each combined finding.")
        elif self.workflow == "factory_certificate":
            notes.append("The comparison examines up to the first 8,000 characters of each readable document.")
            notes.append("Tolerance outcomes are AI-generated interpretations, not deterministic quality-control measurements.")
        elif self.workflow == "tender":
            notes.append("Values merged from several tender documents use the first non-empty value found; review exports for conflicts.")
            if _bool_option(self.options, "includeMarketResearch", "include_market_research", default=True):
                notes.append("Market observations are external research hypotheses, not facts extracted from the tender documents.")
        elif self.workflow == "normalstunden":
            notes.append("Only regular hourly lines are included; detected night, weekend, holiday, and other surcharge lines are excluded.")
            notes.append("No match means no qualifying regular-hours line was found, not that processing failed.")
        elif self.workflow == "invoice":
            notes.append("Extracted invoice values are not reconciled against ERP, purchase-order, or supplier-master data.")
        elif self.workflow == "product_request":
            notes.append("Product grouping is an AI-assisted consolidation and should be checked before sourcing decisions.")

        customization = public_customization(self.options)
        if customization:
            selected_standard = customization.get("standardOutputFields")
            if isinstance(selected_standard, list):
                notes.append(
                    f"The output includes {len(selected_standard):,} selected standard business fields; removed fields are omitted from results and exports."
                )
            if customization.get("instructions") or customization.get("outputFields"):
                notes.append(
                    "Customized output follows the user-defined instructions and requested fields alongside the selected standard result."
                )
                notes.append(
                    "Each custom-analysis request examines up to 30,000 source characters; multi-document requests divide that allowance across sources."
                )

        if self.status == "completed":
            notes.append(
                "AI-generated findings require business review against the retained source documents."
                if self.sources
                else "AI-generated findings require business review against the original source documents."
            )
        return notes


def _bounded_option(
    options: dict[str, Any],
    camel_name: str,
    snake_name: str,
    *,
    default: int,
    low: int,
    high: int,
) -> int:
    try:
        value = int(options.get(camel_name, options.get(snake_name, default)))
    except (TypeError, ValueError):
        value = default
    return max(low, min(high, value))


def _bool_option(
    options: dict[str, Any], camel_name: str, snake_name: str, *, default: bool
) -> bool:
    value = options.get(camel_name, options.get(snake_name, default))
    if isinstance(value, str):
        return value.strip().lower() not in {"0", "false", "no", "off"}
    return bool(value)


class QuestionRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4000)


class QuestionResponse(BaseModel):
    answer: str

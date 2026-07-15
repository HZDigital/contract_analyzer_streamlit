"""API and durable job models."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal, Optional
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


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
    attempt: int = 0

    def public(self) -> dict[str, Any]:
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
            "error": self.error,
            "files": self.files,
            "artifacts": [artifact.public() for artifact in self.artifacts],
            "result": self.result,
        }


class QuestionRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4000)


class QuestionResponse(BaseModel):
    answer: str

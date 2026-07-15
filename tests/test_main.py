from typing import Any

from fastapi.testclient import TestClient

from src.api.auth import get_current_user
from src.api.main import app
from src.api.schemas import CurrentUser, JobRecord


class FakeJobService:
    def __init__(self) -> None:
        self.created: dict[str, Any] | None = None

    def create_job(self, user, workflow, retention, retention_days, options, uploads) -> JobRecord:
        self.created = {
            "user": user,
            "workflow": workflow,
            "retention": retention,
            "retention_days": retention_days,
            "options": options,
            "uploads": uploads,
        }
        return JobRecord(
            owner_oid=user.oid,
            workflow=workflow,
            retention=retention,
            retention_days=retention_days,
            files=[upload.name for upload in uploads],
        )


def _auth_user() -> CurrentUser:
    return CurrentUser(oid="object-id", subject="subject-id", tenant_id="tenant-id")


def _job_form(retention_days: str = "60") -> dict[str, str]:
    return {
        "workflow": "invoice",
        "retention": "temporary",
        "retentionDays": retention_days,
        "retention_days": retention_days,
        "options": "{}",
        "fileRoles": '[{"role":"invoices","name":"invoice.pdf"}]',
        "metadata": "{}",
    }


def test_create_job_accepts_the_spa_multipart_contract() -> None:
    service = FakeJobService()
    app.dependency_overrides[get_current_user] = _auth_user
    try:
        with TestClient(app) as client:
            app.state.job_service = service
            response = client.post(
                "/api/jobs",
                data=_job_form(),
                files=[("files", ("invoice.pdf", b"pdf", "application/pdf"))],
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 201
    assert response.json()["workflow"] == "invoice"
    assert response.json()["files"] == ["invoice.pdf"]
    assert service.created is not None
    assert service.created["retention_days"] == 60
    assert service.created["uploads"][0].role == "invoices"


def test_create_job_rejects_disagreeing_retention_field_aliases() -> None:
    app.dependency_overrides[get_current_user] = _auth_user
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/jobs",
                data={**_job_form(), "retention_days": "59"},
                files=[("files", ("invoice.pdf", b"pdf", "application/pdf"))],
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422
    assert response.json() == {"error": "Retention day values must match."}


def test_unknown_api_route_never_falls_back_to_the_spa() -> None:
    with TestClient(app) as client:
        response = client.get("/api/not-a-route")

    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/json")

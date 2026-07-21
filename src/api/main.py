"""FastAPI application serving the analyzer API and its same-origin React SPA."""

from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Any
from urllib.parse import quote

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile, status
from fastapi.exception_handlers import http_exception_handler
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from .auth import get_current_user
from .customization import CustomizationValidationError, normalize_customization_options
from .jobs import JobDispatcher, JobService
from .schemas import CurrentUser, QuestionRequest, QuestionResponse
from .settings import Settings, get_settings
from .storage import BlobJobStorage
from .uploads import parse_json_field, validate_uploads


APP_ROOT = Path(__file__).resolve().parents[2]
SPA_DIRECTORY = APP_ROOT / "frontend" / "dist"


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    storage = BlobJobStorage(settings)
    service = JobService(storage, settings)
    dispatcher = JobDispatcher(service)
    app.state.job_service = service
    await dispatcher.start()
    try:
        yield
    finally:
        await dispatcher.stop()


app = FastAPI(title="Contract Analyzer", version="1.0.0", lifespan=lifespan)


@app.exception_handler(HTTPException)
async def analyzer_http_exception_handler(request: Request, exc: HTTPException) -> Response:
    if isinstance(exc.detail, str):
        return JSONResponse(status_code=exc.status_code, content={"error": exc.detail})
    return await http_exception_handler(request, exc)


def get_job_service(request: Request) -> JobService:
    return request.app.state.job_service


def _json_object(raw: str, field_name: str) -> dict[str, Any]:
    value = parse_json_field(raw, field_name)
    if not isinstance(value, dict):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"{field_name} must be a JSON object.")
    return value


@app.get("/health")
async def health(settings: Annotated[Settings, Depends(get_settings)]) -> dict[str, Any]:
    """Public liveness endpoint. Protected routes report missing required settings."""

    return {
        "status": "ok",
        "storageConfigured": settings.storage_configured,
        "authConfigured": settings.auth_configured,
    }


@app.get("/api/jobs")
async def list_jobs(
    user: Annotated[CurrentUser, Depends(get_current_user)],
    service: Annotated[JobService, Depends(get_job_service)],
) -> list[dict[str, Any]]:
    jobs = await asyncio.to_thread(service.list_jobs, user)
    return [job.summary_public() for job in jobs]


@app.post("/api/jobs", status_code=status.HTTP_201_CREATED)
async def create_job(
    workflow: Annotated[str, Form(min_length=1, max_length=64)],
    retention: Annotated[str, Form()] = "temporary",
    retention_days: Annotated[str | None, Form(alias="retentionDays")] = None,
    retention_days_snake: Annotated[str | None, Form(alias="retention_days")] = None,
    options_raw: Annotated[str, Form(alias="options")] = "{}",
    file_roles_raw: Annotated[str, Form(alias="fileRoles")] = "[]",
    metadata_raw: Annotated[str | None, Form(alias="metadata")] = None,
    files: Annotated[list[UploadFile], File()] = [],
    user: CurrentUser = Depends(get_current_user),
    service: JobService = Depends(get_job_service),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    try:
        options = normalize_customization_options(_json_object(options_raw, "options"), workflow)
    except CustomizationValidationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    if metadata_raw is not None:
        # Metadata is currently client-side bookkeeping; validate it without persisting document-derived data.
        _json_object(metadata_raw, "metadata")
    if retention_days is not None and retention_days_snake is not None and retention_days != retention_days_snake:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Retention day values must match.")
    supplied_retention_days = retention_days if retention_days is not None else retention_days_snake
    try:
        parsed_retention_days = int(supplied_retention_days) if supplied_retention_days is not None else None
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="retentionDays must be an integer.") from exc
    if parsed_retention_days is not None and parsed_retention_days != 60:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Temporary results are retained for 60 days.")
    uploads = await validate_uploads(workflow, files, file_roles_raw, settings)
    try:
        job = await asyncio.to_thread(
            service.create_job,
            user,
            workflow,
            retention,
            parsed_retention_days,
            options,
            uploads,
        )
    finally:
        for uploaded_file in files:
            await uploaded_file.close()
    return job.public()


@app.get("/api/jobs/{job_id}")
async def get_job(
    job_id: str,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    service: Annotated[JobService, Depends(get_job_service)],
) -> dict[str, Any]:
    job = await asyncio.to_thread(service.get_job, user, job_id)
    return job.public()


@app.delete("/api/jobs/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_job(
    job_id: str,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    service: Annotated[JobService, Depends(get_job_service)],
) -> Response:
    await asyncio.to_thread(service.delete_job, user, job_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.get("/api/jobs/{job_id}/artifacts/{artifact_id}")
async def download_artifact(
    job_id: str,
    artifact_id: str,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    service: Annotated[JobService, Depends(get_job_service)],
) -> Response:
    artifact, data = await asyncio.to_thread(service.get_artifact, user, job_id, artifact_id)
    filename = quote(artifact.name, safe="")
    return Response(
        content=data,
        media_type=artifact.content_type,
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{filename}"},
    )


@app.get("/api/jobs/{job_id}/sources/{source_id}")
async def get_source(
    job_id: str,
    source_id: str,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    service: Annotated[JobService, Depends(get_job_service)],
) -> Response:
    source, data = await asyncio.to_thread(service.get_source, user, job_id, source_id)
    filename = quote(source.name, safe="")
    disposition = "inline" if source.content_type == "application/pdf" else "attachment"
    return Response(
        content=data,
        media_type=source.content_type,
        headers={
            "Cache-Control": "private, no-store",
            "Content-Disposition": f"{disposition}; filename*=UTF-8''{filename}",
            "X-Content-Type-Options": "nosniff",
        },
    )


@app.post("/api/jobs/{job_id}/questions")
async def ask_question(
    job_id: str,
    payload: QuestionRequest,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    service: Annotated[JobService, Depends(get_job_service)],
) -> QuestionResponse:
    answer = await asyncio.to_thread(service.answer_question, user, job_id, payload.question)
    return QuestionResponse(answer=answer)


if SPA_DIRECTORY.is_dir():
    assets_directory = SPA_DIRECTORY / "assets"
    if assets_directory.is_dir():
        app.mount("/assets", StaticFiles(directory=assets_directory), name="assets")


@app.get("/{path:path}", include_in_schema=False)
async def serve_spa(path: str) -> Response:
    """Serve an existing static file or the SPA entrypoint, never an API fallback."""

    if path.startswith("api/"):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API route not found.")
    candidate = (SPA_DIRECTORY / path).resolve()
    if path and SPA_DIRECTORY.is_dir() and candidate.is_relative_to(SPA_DIRECTORY.resolve()) and candidate.is_file():
        return FileResponse(candidate)
    index = SPA_DIRECTORY / "index.html"
    if index.is_file():
        return FileResponse(index)
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Analyzer frontend is not built.")

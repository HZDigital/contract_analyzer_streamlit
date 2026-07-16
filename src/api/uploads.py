"""Upload validation and safe Normalstunden ZIP expansion."""

from __future__ import annotations

import json
import stat
import zipfile
from dataclasses import dataclass
from io import BytesIO
from pathlib import PurePosixPath
from typing import Iterable

from fastapi import HTTPException, UploadFile, status

from .schemas import FileRole
from .settings import Settings


WORKFLOW_ROLES: dict[str, dict[str, tuple[set[str], int, int | None]]] = {
    "product_request": {"requests": ({".pdf"}, 1, None)},
    "invoice": {"invoices": ({".pdf"}, 1, None)},
    "normalstunden": {
        "normalstundenPdfs": ({".pdf"}, 1, None),
        "normalstundenArchive": ({".zip"}, 1, 1),
    },
    "detailed_contract": {"contracts": ({".pdf"}, 1, None)},
    "tender": {
        "tenderDocuments": ({".pdf"}, 1, None),
        "tenderTemplate": ({".xlsx"}, 1, 1),
    },
    "cooperation_review": {
        "supplierAgreements": ({".pdf", ".doc", ".docx"}, 1, None),
        "standardContract": ({".pdf"}, 1, 1),
    },
    "factory_certificate": {"comparisonDocuments": ({".pdf"}, 2, None)},
    "large_scanner": {"contract": ({".pdf"}, 1, 1)},
}


@dataclass
class ValidatedUpload:
    name: str
    role: str
    content_type: str | None
    data: bytes
    supplier_hint: str = ""


def _bad_request(message: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=message)


def safe_filename(name: str | None) -> str:
    if not name:
        raise _bad_request("Every uploaded file needs a filename.")
    cleaned = name.replace("\\", "/")
    path = PurePosixPath(cleaned)
    if path.name != cleaned or path.name in {"", ".", ".."} or "\x00" in cleaned:
        raise _bad_request("Invalid upload filename.")
    return path.name


def parse_json_field(raw: str, field_name: str) -> object:
    try:
        return json.loads(raw)
    except (TypeError, json.JSONDecodeError) as exc:
        raise _bad_request(f"{field_name} must be valid JSON.") from exc


async def validate_uploads(
    workflow: str,
    files: list[UploadFile],
    file_roles_raw: str,
    settings: Settings,
) -> list[ValidatedUpload]:
    specification = WORKFLOW_ROLES.get(workflow)
    if specification is None:
        raise _bad_request("Unsupported workflow.")
    if not files or len(files) > settings.max_files_per_job:
        raise _bad_request(f"Upload between 1 and {settings.max_files_per_job} files.")

    role_payload = parse_json_field(file_roles_raw, "fileRoles")
    try:
        file_roles = [FileRole.model_validate(item) for item in role_payload]  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        raise _bad_request("fileRoles must contain role and name entries.") from exc
    if len(file_roles) != len(files):
        raise _bad_request("Each uploaded file must have exactly one role.")

    roles_by_name: dict[str, str] = {}
    normalized_names: set[str] = set()
    for item in file_roles:
        normalized_name = item.name.casefold()
        if normalized_name in normalized_names:
            raise _bad_request("Duplicate uploaded filenames are not supported.")
        normalized_names.add(normalized_name)
        roles_by_name[item.name] = item.role

    validated: list[ValidatedUpload] = []
    uploaded_names: set[str] = set()
    total_size = 0
    for upload in files:
        name = safe_filename(upload.filename)
        normalized_name = name.casefold()
        if normalized_name in uploaded_names:
            raise _bad_request("Duplicate uploaded filenames are not supported.")
        uploaded_names.add(normalized_name)
        role = roles_by_name.get(name)
        if role is None or role not in specification:
            raise _bad_request(f"{name} has an invalid role for this workflow.")
        suffix = PurePosixPath(name).suffix.lower()
        allowed_suffixes, _, _ = specification[role]
        if suffix not in allowed_suffixes:
            raise _bad_request(f"{name} is not an allowed file type for {role}.")
        data = await upload.read(settings.max_file_bytes + 1)
        if not data or len(data) > settings.max_file_bytes:
            raise _bad_request(f"{name} exceeds the per-file upload limit.")
        if suffix in {".docx", ".xlsx"}:
            _validate_ooxml_container(data, name, settings)
        total_size += len(data)
        if total_size > settings.max_total_upload_bytes:
            raise _bad_request("The combined upload exceeds the job limit.")
        validated.append(ValidatedUpload(name=name, role=role, content_type=upload.content_type, data=data))

    _validate_role_counts(workflow, validated, specification)
    return validated


def _safe_archive_path(info: zipfile.ZipInfo) -> PurePosixPath:
    name = info.filename.replace("\\", "/")
    path = PurePosixPath(name)
    if "\x00" in name or path.is_absolute() or ".." in path.parts or not path.name:
        raise _bad_request("The ZIP archive contains an unsafe path.")
    if info.flag_bits & 0x1:
        raise _bad_request("Encrypted ZIP archives are not supported.")
    if stat.S_ISLNK(info.external_attr >> 16):
        raise _bad_request("ZIP archives containing symbolic links are not supported.")
    return path


def _validate_ooxml_container(data: bytes, name: str, settings: Settings) -> None:
    """Reject compressed Office documents that exceed the same ZIP safety limits."""

    if len(data) > settings.max_zip_compressed_bytes:
        raise _bad_request(f"{name} exceeds the compressed OOXML limit.")
    try:
        archive = zipfile.ZipFile(BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise _bad_request(f"{name} is not a valid OOXML document.") from exc

    uncompressed_size = 0
    with archive:
        infos = archive.infolist()
        if len(infos) > settings.max_zip_files:
            raise _bad_request(f"{name} contains too many OOXML entries.")
        for info in infos:
            _safe_archive_path(info)
            if info.is_dir():
                continue
            if info.file_size > settings.max_file_bytes:
                raise _bad_request(f"{name} contains an OOXML entry exceeding the per-file upload limit.")
            uncompressed_size += info.file_size
            if uncompressed_size > settings.max_zip_uncompressed_bytes:
                raise _bad_request(f"{name} exceeds the uncompressed OOXML limit.")


def _validate_role_counts(
    workflow: str,
    uploads: Iterable[ValidatedUpload],
    specification: dict[str, tuple[set[str], int, int | None]],
) -> None:
    counts: dict[str, int] = {}
    for upload in uploads:
        counts[upload.role] = counts.get(upload.role, 0) + 1
    if workflow == "normalstunden" and bool(counts.get("normalstundenPdfs")) == bool(counts.get("normalstundenArchive")):
        raise _bad_request("Choose either Normalstunden PDFs or one ZIP archive.")
    for role, (_, minimum, maximum) in specification.items():
        count = counts.get(role, 0)
        if workflow == "normalstunden" and count == 0:
            continue
        if count < minimum or (maximum is not None and count > maximum):
            raise _bad_request(f"Invalid number of files for {role}.")


def expand_normalstunden_archive(data: bytes, settings: Settings, include_subfolders: bool) -> list[ValidatedUpload]:
    """Expand a ZIP without ever writing untrusted archive members to disk."""

    if len(data) > settings.max_zip_compressed_bytes:
        raise _bad_request("The ZIP archive exceeds the compressed size limit.")
    try:
        archive = zipfile.ZipFile(BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise _bad_request("The Normalstunden archive is not a valid ZIP file.") from exc

    uploads: list[ValidatedUpload] = []
    uncompressed_size = 0
    with archive:
        infos = archive.infolist()
        if len(infos) > settings.max_zip_files:
            raise _bad_request("The ZIP archive contains too many entries.")
        for info in infos:
            path = _safe_archive_path(info)
            if info.is_dir():
                continue
            if path.suffix.lower() != ".pdf":
                raise _bad_request("Normalstunden ZIP archives may contain PDF files only.")
            uncompressed_size += info.file_size
            if uncompressed_size > settings.max_zip_uncompressed_bytes:
                raise _bad_request("The ZIP archive exceeds the uncompressed size limit.")
            if info.file_size > settings.max_file_bytes:
                raise _bad_request(f"{path.name} exceeds the per-file upload limit.")
            if not include_subfolders and len(path.parts) > 1:
                continue
            member = archive.read(info)
            supplier_hint = "" if path.parent == PurePosixPath(".") else path.parent.as_posix()
            uploads.append(
                ValidatedUpload(
                    name=path.name,
                    role="normalstundenPdfs",
                    content_type="application/pdf",
                    data=member,
                    supplier_hint=supplier_hint,
                )
            )
    if not uploads:
        raise _bad_request("The ZIP archive contains no eligible PDF files.")
    return uploads

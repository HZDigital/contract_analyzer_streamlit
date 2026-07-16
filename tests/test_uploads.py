import asyncio
from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

import pytest
from fastapi import HTTPException, UploadFile
from starlette.datastructures import Headers

from src.api.settings import Settings
from src.api.uploads import expand_normalstunden_archive, validate_uploads


def _upload(name: str, data: bytes, content_type: str = "application/pdf") -> UploadFile:
    return UploadFile(file=BytesIO(data), filename=name, headers=Headers({"content-type": content_type}))


def _zip(entries: dict[str, bytes]) -> bytes:
    output = BytesIO()
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        for name, data in entries.items():
            archive.writestr(name, data)
    return output.getvalue()


def test_validate_uploads_rejects_a_role_not_allowed_by_the_workflow() -> None:
    async def validate() -> None:
        await validate_uploads(
            "invoice",
            [_upload("invoice.pdf", b"pdf")],
            '[{"role":"requests","name":"invoice.pdf"}]',
            Settings(),
        )

    with pytest.raises(HTTPException, match="invalid role"):
        asyncio.run(validate())


def test_validate_uploads_rejects_case_insensitive_duplicate_names() -> None:
    async def validate() -> None:
        await validate_uploads(
            "invoice",
            [_upload("invoice.pdf", b"one"), _upload("Invoice.pdf", b"two")],
            '[{"role":"invoices","name":"invoice.pdf"},{"role":"invoices","name":"Invoice.pdf"}]',
            Settings(),
        )

    with pytest.raises(HTTPException, match="Duplicate uploaded filenames"):
        asyncio.run(validate())


def test_validate_uploads_rejects_duplicate_actual_upload_names() -> None:
    async def validate() -> None:
        await validate_uploads(
            "invoice",
            [_upload("invoice.pdf", b"one"), _upload("invoice.pdf", b"two")],
            '[{"role":"invoices","name":"invoice.pdf"},{"role":"invoices","name":"other.pdf"}]',
            Settings(),
        )

    with pytest.raises(HTTPException, match="Duplicate uploaded filenames"):
        asyncio.run(validate())


def test_normalstunden_zip_rejects_path_traversal_and_non_pdf_entries() -> None:
    settings = Settings()

    with pytest.raises(HTTPException, match="unsafe path"):
        expand_normalstunden_archive(_zip({"../invoice.pdf": b"pdf"}), settings, include_subfolders=True)

    with pytest.raises(HTTPException, match="PDF files only"):
        expand_normalstunden_archive(_zip({"invoice.txt": b"not a PDF"}), settings, include_subfolders=True)


def test_normalstunden_zip_honors_the_subfolder_option() -> None:
    settings = Settings()
    files = expand_normalstunden_archive(
        _zip({"root.pdf": b"root", "nested/nested.pdf": b"nested"}),
        settings,
        include_subfolders=False,
    )

    assert [file.name for file in files] == ["root.pdf"]


def test_normalstunden_zip_preserves_the_validated_parent_as_supplier_hint() -> None:
    files = expand_normalstunden_archive(
        _zip({"supplier-a/january/invoice.pdf": b"invoice"}),
        Settings(),
        include_subfolders=True,
    )

    assert files[0].name == "invoice.pdf"
    assert files[0].supplier_hint == "supplier-a/january"


def test_validate_uploads_rejects_an_expanding_ooxml_document() -> None:
    settings = Settings.model_construct(
        max_file_bytes=1024,
        max_total_upload_bytes=2048,
        max_zip_files=10,
        max_zip_uncompressed_bytes=2048,
        max_zip_compressed_bytes=2048,
    )
    document = _zip({"[Content_Types].xml": b"content", "xl/sharedStrings.xml": b"x" * 4096})

    async def validate() -> None:
        await validate_uploads(
            "tender",
            [_upload("template.xlsx", document, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")],
            '[{"role":"tenderTemplate","name":"template.xlsx"}]',
            settings,
        )

    with pytest.raises(HTTPException, match="OOXML entry"):
        asyncio.run(validate())

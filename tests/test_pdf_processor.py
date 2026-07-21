from __future__ import annotations

import base64
from io import BytesIO
from types import SimpleNamespace

import httpx
import pytest
from PIL import Image

from src.api.settings import Settings
from src.utils import pdf_processor


class _Response:
    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self.payload


class _Page:
    def __init__(
        self,
        png: bytes,
        *,
        text: str = "",
        has_images: bool = True,
        image_coverage: float = 1,
    ) -> None:
        self.png = png
        self.text = text
        self.has_images = has_images
        self.image_coverage = image_coverage
        self.rect = pdf_processor.fitz.Rect(0, 0, 100, 100)

    def get_text(self) -> str:
        return self.text

    def get_images(self, *, full: bool) -> list[tuple[str]]:
        return [("image",)] if self.has_images else []

    def get_image_rects(self, image):  # noqa: ANN001, ANN201
        if not self.has_images:
            return []
        return [pdf_processor.fitz.Rect(0, 0, 100, 100 * self.image_coverage)]

    def get_pixmap(self, *, matrix):  # noqa: ANN001
        return SimpleNamespace(tobytes=lambda _format: self.png)


class _Document:
    def __init__(self, pages: list[_Page]) -> None:
        self.pages = pages
        self.closed = False

    def __iter__(self):  # noqa: ANN201
        return iter(self.pages)

    def close(self) -> None:
        self.closed = True


def _mistral_settings() -> SimpleNamespace:
    return SimpleNamespace(
        mistral_document_ai_configured=True,
        azure_mistral_document_ai_endpoint="https://mistral.example/v1",
        azure_mistral_document_ai_api_key="test-key",
        azure_mistral_document_ai_model="mistral-document-ai-2512",
        azure_mistral_document_ai_timeout_seconds=45,
    )


def _png() -> bytes:
    output = BytesIO()
    Image.new("RGB", (2, 2), color="white").save(output, format="PNG")
    return output.getvalue()


def test_mistral_document_ai_settings_are_enabled_only_with_endpoint_and_key() -> None:
    assert not Settings(
        AZURE_MISTRAL_DOCUMENT_AI_ENDPOINT="",
        AZURE_MISTRAL_DOCUMENT_AI_API_KEY="",
    ).mistral_document_ai_configured
    assert Settings(
        AZURE_MISTRAL_DOCUMENT_AI_ENDPOINT="https://mistral.example",
        AZURE_MISTRAL_DOCUMENT_AI_API_KEY="key",
    ).mistral_document_ai_configured


def test_mistral_document_ai_url_normalizes_endpoint_variants() -> None:
    assert pdf_processor._mistral_document_ai_url("https://mistral.example") == "https://mistral.example/v1/ocr"
    assert pdf_processor._mistral_document_ai_url("https://mistral.example/v1/") == "https://mistral.example/v1/ocr"
    assert pdf_processor._mistral_document_ai_url("https://mistral.example/v1/ocr") == "https://mistral.example/v1/ocr"


def test_mistral_document_ai_sends_a_base64_png_and_returns_markdown(monkeypatch) -> None:
    monkeypatch.setattr(pdf_processor, "get_settings", _mistral_settings)
    request: dict = {}

    def post(url, **kwargs):  # noqa: ANN001
        request["url"] = url
        request.update(kwargs)
        return _Response({"pages": [{"markdown": "# Recognized text\n"}]})

    monkeypatch.setattr(pdf_processor.httpx, "post", post)

    assert pdf_processor._extract_text_with_mistral_document_ai(Image.open(BytesIO(_png()))) == "# Recognized text"
    assert request["url"] == "https://mistral.example/v1/ocr"
    assert request["headers"] == {
        "Authorization": "Bearer test-key",
        "Content-Type": "application/json",
    }
    assert request["json"]["model"] == "mistral-document-ai-2512"
    assert request["json"]["document"]["type"] == "image_url"
    encoded_image = request["json"]["document"]["image_url"].removeprefix("data:image/png;base64,")
    assert base64.b64decode(encoded_image).startswith(b"\x89PNG")
    assert request["timeout"] == 45


def test_unconfigured_mistral_does_not_make_a_request(monkeypatch) -> None:
    monkeypatch.setattr(
        pdf_processor,
        "get_settings",
        lambda: SimpleNamespace(mistral_document_ai_configured=False),
    )
    monkeypatch.setattr(pdf_processor.httpx, "post", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError()))

    assert pdf_processor._extract_text_with_mistral_document_ai(Image.open(BytesIO(_png()))) == ""


def test_mistral_failure_falls_back_to_tesseract(monkeypatch) -> None:
    monkeypatch.setattr(pdf_processor, "get_settings", _mistral_settings)
    monkeypatch.setattr(
        pdf_processor.httpx,
        "post",
        lambda *args, **kwargs: (_ for _ in ()).throw(httpx.ReadTimeout("timed out")),
    )
    monkeypatch.setattr(pdf_processor.pytesseract, "image_to_string", lambda image: "Tesseract text\n")

    assert pdf_processor._extract_text_from_page_with_ocr(_Page(_png()), 1) == "Tesseract text"


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"pages": []},
        {"pages": "not-a-list"},
        {"pages": [{}]},
        {"pages": [{"markdown": None}]},
        {"pages": [{"markdown": 42}]},
    ],
)
def test_malformed_mistral_response_falls_back_to_tesseract(monkeypatch, payload: dict) -> None:
    monkeypatch.setattr(pdf_processor, "get_settings", _mistral_settings)
    monkeypatch.setattr(pdf_processor.httpx, "post", lambda *args, **kwargs: _Response(payload))
    monkeypatch.setattr(pdf_processor.pytesseract, "image_to_string", lambda image: "Tesseract text\n")

    assert pdf_processor._extract_text_from_page_with_ocr(_Page(_png()), 1) == "Tesseract text"


def test_invalid_mistral_json_falls_back_to_tesseract(monkeypatch) -> None:
    class _InvalidJsonResponse(_Response):
        def json(self) -> dict:
            raise ValueError("invalid JSON")

    monkeypatch.setattr(pdf_processor, "get_settings", _mistral_settings)
    monkeypatch.setattr(pdf_processor.httpx, "post", lambda *args, **kwargs: _InvalidJsonResponse({}))
    monkeypatch.setattr(pdf_processor.pytesseract, "image_to_string", lambda image: "Tesseract text\n")

    assert pdf_processor._extract_text_from_page_with_ocr(_Page(_png()), 1) == "Tesseract text"


def test_native_text_page_does_not_call_mistral(monkeypatch) -> None:
    native_text = "Short native text."
    document = _Document([_Page(_png(), text=native_text, image_coverage=0.1)])
    monkeypatch.setattr(pdf_processor.fitz, "open", lambda **kwargs: document)
    monkeypatch.setattr(pdf_processor, "get_settings", _mistral_settings)
    monkeypatch.setattr(
        pdf_processor.httpx,
        "post",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("Mistral should not be called")),
    )

    assert pdf_processor.extract_text_from_pdf(b"pdf") == native_text
    assert document.closed


def test_image_heavy_page_with_sparse_native_text_calls_mistral(monkeypatch) -> None:
    document = _Document([_Page(_png(), text="Page footer with a document reference number 12345")])
    monkeypatch.setattr(pdf_processor.fitz, "open", lambda **kwargs: document)
    monkeypatch.setattr(pdf_processor, "get_settings", _mistral_settings)
    request_count = 0

    def post(*args, **kwargs):  # noqa: ANN002, ANN003
        nonlocal request_count
        request_count += 1
        return _Response({"pages": [{"markdown": "Mistral text"}]})

    monkeypatch.setattr(pdf_processor.httpx, "post", post)

    assert pdf_processor.extract_text_from_pdf(b"pdf") == "Mistral text"
    assert request_count == 1
    assert document.closed


def test_empty_pdf_fallback_keeps_small_logo_pages_local(monkeypatch) -> None:
    document = _Document([_Page(_png(), image_coverage=0.1)])
    monkeypatch.setattr(pdf_processor.fitz, "open", lambda **kwargs: document)
    monkeypatch.setattr(pdf_processor, "get_settings", _mistral_settings)
    monkeypatch.setattr(
        pdf_processor.httpx,
        "post",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("Mistral should not be called")),
    )
    monkeypatch.setattr(pdf_processor.pytesseract, "image_to_string", lambda image: "Tesseract text\n")

    assert pdf_processor.extract_text_from_pdf(b"pdf") == "Tesseract text\n"
    assert document.closed


def test_empty_page_records_keep_small_logo_pages_local(monkeypatch) -> None:
    document = _Document([_Page(_png(), image_coverage=0.1)])
    monkeypatch.setattr(pdf_processor.fitz, "open", lambda **kwargs: document)
    monkeypatch.setattr(pdf_processor, "get_settings", _mistral_settings)
    monkeypatch.setattr(
        pdf_processor.httpx,
        "post",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("Mistral should not be called")),
    )
    monkeypatch.setattr(pdf_processor.pytesseract, "image_to_string", lambda image: "Tesseract text\n")

    pages = pdf_processor.extract_pdf_pages(b"pdf")

    assert pages == [{"page": 1, "text": "Tesseract text", "extraction_method": "ocr", "char_count": 14}]
    assert document.closed

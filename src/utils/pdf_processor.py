"""
PDF processing utilities for text extraction and OCR.
"""

import base64
import logging

import fitz  # PyMuPDF
import httpx
import pytesseract
from io import BytesIO
from PIL import Image
from typing import BinaryIO, Optional, Union

from src.api.settings import get_settings


logger = logging.getLogger(__name__)

MIN_OCR_IMAGE_COVERAGE = 0.5
MIN_NATIVE_TEXT_CHARACTERS = 120


def _read_uploaded_bytes(file: Union[BinaryIO, bytes]) -> Optional[bytes]:
    """Read bytes from file-like objects or raw bytes."""
    if isinstance(file, (bytes, bytearray)):
        return bytes(file)
    if hasattr(file, "getvalue") and callable(getattr(file, "getvalue")):
        return file.getvalue()
    if hasattr(file, "read") and callable(getattr(file, "read")):
        try:
            if hasattr(file, "seek") and callable(getattr(file, "seek")):
                file.seek(0)
        except Exception:
            pass
        return file.read()
    return None


def extract_pdf_pages(file: Union[BinaryIO, bytes]) -> list[dict]:
    """
    Extract PDF text as page-level records for large-contract analysis.

    Returns:
        list[dict]: Records with page, text, extraction_method, and char_count.
    """
    try:
        pdf_bytes = _read_uploaded_bytes(file)
    except Exception as e:
        return [{"page": 0, "text": f"[PDF Read Error: {e}]", "extraction_method": "error", "char_count": 0}]

    if not pdf_bytes:
        return [{"page": 0, "text": "[PDF Error: Empty upload]", "extraction_method": "error", "char_count": 0}]

    doc = None
    pages = []
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        for page_num, page in enumerate(doc, 1):
            page_text = page.get_text()
            extraction_method = "native"
            if _should_ocr_page(page, page_text):
                ocr_text = _extract_text_from_page_with_ocr(page, page_num)
                if ocr_text.strip():
                    page_text = ocr_text
                    extraction_method = "ocr"
                else:
                    extraction_method = "native_empty_ocr_failed"

            pages.append({
                "page": page_num,
                "text": page_text,
                "extraction_method": extraction_method,
                "char_count": len(page_text),
            })

        if not any(page["text"].strip() for page in pages):
            pages = []
            for page_num, page in enumerate(doc, 1):
                native_text = page.get_text()
                page_text = _extract_text_from_page_with_ocr(
                    page,
                    page_num,
                    use_mistral=_should_ocr_page(page, native_text),
                )
                pages.append({
                    "page": page_num,
                    "text": page_text,
                    "extraction_method": "ocr",
                    "char_count": len(page_text),
                })
    except Exception as e:
        return [{"page": 0, "text": f"[PDF Error: {e}]", "extraction_method": "error", "char_count": 0}]
    finally:
        if doc is not None:
            doc.close()

    return pages


def extract_text_from_pdf(file: Union[BinaryIO, bytes]) -> str:
    """
    Extract text from a PDF file using various methods.
    
    Args:
        file: Binary file object (uploaded PDF) or raw bytes
        
    Returns:
        str: Extracted text content
    """
    # Obtain PDF bytes robustly from file-like inputs or raw bytes.
    try:
        pdf_bytes = _read_uploaded_bytes(file)
    except Exception as e:
        return f"[PDF Read Error: {e}]"

    if not pdf_bytes:
        return "[PDF Error: Empty upload]"
    

    doc = None
    try:
        # Try native text extraction first, but OCR image-only pages in mixed PDFs.
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        full_text = ""
        for page_num, page in enumerate(doc, 1):
            page_text = page.get_text()
            if _should_ocr_page(page, page_text):
                ocr_text = _extract_text_from_page_with_ocr(page, page_num)
                full_text += ocr_text if ocr_text.strip() else page_text
            else:
                full_text += page_text
        # If no text was extracted, fallback to OCR
        if not full_text.strip():
            full_text = _extract_text_with_ocr(pdf_bytes)
    except fitz.FileDataError as error:
        raise ValueError("The PDF could not be opened.") from error
    finally:
        if doc is not None:
            doc.close()

    return full_text


def _extract_text_with_ocr(pdf_bytes: bytes) -> str:
    """
    Extract text using OCR when native extraction fails.
    Tries Mistral Document AI first (if configured), falls back to Tesseract.
    Uses higher DPI (300) for better scanned document quality.
    
    Args:
        pdf_bytes: PDF content
        
    Returns:
        str: OCR extracted text
    """
    doc = None    
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        ocr_text = ""

        for page_num, page in enumerate(doc, 1):
            native_text = page.get_text()
            page_text = _extract_text_from_page_with_ocr(
                page,
                page_num,
                use_mistral=_should_ocr_page(page, native_text),
            )
            if page_text:
                ocr_text += page_text + "\n"

        return ocr_text if ocr_text.strip() else "[OCR Error: No text extracted from any page]"
    except Exception as ocr_err:  # noqa: BLE001
        return f"[OCR Error: {ocr_err}]"
    finally:
        if doc is not None:
            doc.close()


def _should_ocr_page(page, page_text: str) -> bool:
    """OCR image-dominated pages that lack a useful native text layer."""
    images = page.get_images(full=True)
    if not images:
        return False

    try:
        page_area = page.rect.get_area()
        image_area = sum(
            rect.get_area()
            for image in images
            for rect in page.get_image_rects(image[0])
        )
    except Exception:  # noqa: BLE001
        # Avoid sending pages to the hosted provider when their image coverage
        # cannot be established.
        return False

    if not page_area or min(image_area / page_area, 1) < MIN_OCR_IMAGE_COVERAGE:
        return False

    return len(page_text.strip()) < MIN_NATIVE_TEXT_CHARACTERS


def _mistral_document_ai_url(endpoint: str) -> str:
    """Normalize the Azure Foundry endpoint to Mistral's OCR route."""
    normalized = endpoint.rstrip("/")
    if normalized.endswith("/v1/ocr"):
        return normalized
    if normalized.endswith("/v1"):
        return f"{normalized}/ocr"
    return f"{normalized}/v1/ocr"


def _extract_text_with_mistral_document_ai(image: Image.Image) -> str:
    """Return Markdown from Azure Mistral Document AI, or an empty fallback value."""
    settings = get_settings()
    if not settings.mistral_document_ai_configured:
        return ""

    endpoint = settings.azure_mistral_document_ai_endpoint
    api_key = settings.azure_mistral_document_ai_api_key
    if not endpoint or not api_key:
        return ""

    try:
        image_buffer = BytesIO()
        image.save(image_buffer, format="PNG")
        image_data = base64.b64encode(image_buffer.getvalue()).decode("ascii")
        payload = {
            "model": settings.azure_mistral_document_ai_model,
            "document": {
                "type": "image_url",
                "image_url": f"data:image/png;base64,{image_data}",
            },
        }
        response = httpx.post(
            _mistral_document_ai_url(endpoint),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=settings.azure_mistral_document_ai_timeout_seconds,
        )
        response.raise_for_status()
        response_body = response.json()
        pages = response_body.get("pages") if isinstance(response_body, dict) else None
        if not isinstance(pages, list) or not pages:
            return ""
        markdown = pages[0].get("markdown") if isinstance(pages[0], dict) else None
        return markdown.strip() if isinstance(markdown, str) else ""
    except (httpx.HTTPError, ValueError, TypeError):
        # Provider failures must not expose their response to browser users.
        logger.warning("Mistral Document AI OCR request failed; falling back to Tesseract")
        return ""


def _extract_text_from_page_with_ocr(page, page_num: int, *, use_mistral: bool = True) -> str:
    """Extract text from one rendered PDF page using OCR."""
    try:
        # Render at high DPI (300) for scanned documents.
        mat = fitz.Matrix(300 / 72, 300 / 72)
        pix = page.get_pixmap(matrix=mat)
        image = Image.open(BytesIO(pix.tobytes("png")))
    except Exception:  # noqa: BLE001
        # A damaged image stream must not prevent native text from other pages.
        return ""

    mistral_text = _extract_text_with_mistral_document_ai(image) if use_mistral else ""
    if mistral_text:
        return mistral_text

    try:
        return pytesseract.image_to_string(image).strip()
    except Exception:  # noqa: BLE001
        return ""


def extract_text_from_docx(file: Union[BinaryIO, bytes]) -> str:
    """
    Extract text from a Word document (.docx).
    
    Args:
        file: Binary file object (uploaded DOCX) or raw bytes
        
    Returns:
        str: Extracted text content
    """
    try:
        from docx import Document
    except ImportError:
        return "[Error: python-docx not installed. Run: pip install python-docx]"
    
    try:
        # Handle different input types
        if isinstance(file, (bytes, bytearray)):
            doc_bytes = BytesIO(bytes(file))
        elif hasattr(file, "getvalue") and callable(getattr(file, "getvalue")):
            doc_bytes = BytesIO(file.getvalue())
        elif hasattr(file, "read") and callable(getattr(file, "read")):
            try:
                if hasattr(file, "seek") and callable(getattr(file, "seek")):
                    file.seek(0)
            except Exception:
                pass
            doc_bytes = BytesIO(file.read())
        else:
            return "[Error: Invalid file format]"
        
        # Open the Word document
        doc = Document(doc_bytes)
        
        # Extract all paragraphs
        full_text = []
        for paragraph in doc.paragraphs:
            if paragraph.text.strip():
                full_text.append(paragraph.text)
        
        # Extract text from tables
        for table in doc.tables:
            for row in table.rows:
                row_text = []
                for cell in row.cells:
                    if cell.text.strip():
                        row_text.append(cell.text)
                if row_text:
                    full_text.append(" | ".join(row_text))
        
        return "\n".join(full_text)
    
    except Exception as e:
        return f"[Word Document Error: {e}]"


def extract_text_from_file(file: Union[BinaryIO, bytes], filename: str) -> str:
    """
    Extract text from a file (PDF or Word document) based on file extension.
    
    Args:
        file: Binary file object or raw bytes
        filename: Name of the file to determine type
        
    Returns:
        str: Extracted text content
    """
    filename_lower = filename.lower()
    
    if filename_lower.endswith('.pdf'):
        return extract_text_from_pdf(file)
    elif filename_lower.endswith('.docx'):
        return extract_text_from_docx(file)
    elif filename_lower.endswith('.doc'):
        # Old .doc format - try docx parser anyway (may not work)
        return extract_text_from_docx(file)
    else:
        return f"[Error: Unsupported file format for {filename}]"

"""
PDF processing utilities for text extraction and OCR.
"""

import os
import tempfile
import fitz  # PyMuPDF
import pytesseract
from io import BytesIO
from PIL import Image
from datetime import datetime
from typing import BinaryIO, Optional, Union

# Optional: DeepSeek-OCR via transformers (local model, no API key needed)
try:
    from transformers import AutoModel, AutoTokenizer
    import torch
    _transformers_available = True
except ImportError:
    _transformers_available = False

_deepseek_model = None
_deepseek_tokenizer = None
_deepseek_load_attempted = False


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
                page_text = _extract_text_from_page_with_ocr(page, page_num)
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
    Tries DeepSeek-OCR first (if available), falls back to Tesseract.
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
            page_text = _extract_text_from_page_with_ocr(page, page_num)
            if page_text:
                ocr_text += page_text + "\n"

        return ocr_text if ocr_text.strip() else "[OCR Error: No text extracted from any page]"
    except Exception as ocr_err:  # noqa: BLE001
        return f"[OCR Error: {ocr_err}]"
    finally:
        if doc is not None:
            doc.close()


def _should_ocr_page(page, page_text: str) -> bool:
    """OCR pages that are mostly image content with no useful text layer."""
    return bool(page.get_images(full=True)) and len(page_text.strip()) < 30


def _load_deepseek_ocr_model():
    """Load the baked DeepSeek model without attempting any network access."""
    global _deepseek_model, _deepseek_tokenizer, _deepseek_load_attempted

    if _deepseek_model is not None and _deepseek_tokenizer is not None:
        return _deepseek_tokenizer, _deepseek_model
    if _deepseek_load_attempted:
        raise RuntimeError("DeepSeek OCR model is not available locally")

    _deepseek_load_attempted = True
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"

    model_name = "deepseek-ai/DeepSeek-OCR"
    _deepseek_tokenizer = AutoTokenizer.from_pretrained(
        model_name,
        trust_remote_code=True,
        local_files_only=True,
    )

    model_kwargs = {
        "trust_remote_code": True,
        "use_safetensors": True,
        "local_files_only": True,
    }

    if torch.cuda.is_available():
        model_kwargs["torch_dtype"] = torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16
        try:
            _deepseek_model = AutoModel.from_pretrained(
                model_name,
                _attn_implementation="flash_attention_2",
                **model_kwargs,
            ).cuda()
        except Exception:  # noqa: BLE001
            _deepseek_model = AutoModel.from_pretrained(
                model_name,
                device_map="auto",
                **model_kwargs,
            )
    else:
        _deepseek_model = AutoModel.from_pretrained(
            model_name,
            device_map="auto",
            **model_kwargs,
        )

    _deepseek_model = _deepseek_model.eval()
    return _deepseek_tokenizer, _deepseek_model


def _extract_text_from_page_with_ocr(page, page_num: int) -> str:
    """Extract text from one rendered PDF page using OCR."""
    try:
        # Render at high DPI (300) for scanned documents.
        mat = fitz.Matrix(300 / 72, 300 / 72)
        pix = page.get_pixmap(matrix=mat)
        image = Image.open(BytesIO(pix.tobytes("png")))
    except Exception:  # noqa: BLE001
        # A damaged image stream must not prevent native text from other pages.
        return ""

    if _transformers_available:
        temp_img_path = None
        try:
            tokenizer, model = _load_deepseek_ocr_model()

            with tempfile.NamedTemporaryFile(suffix=f"_{page_num}.png", delete=False) as image_file:
                temp_img_path = image_file.name
            image.save(temp_img_path)

            prompt = "<image>\n<|grounding|>Convert the document to markdown. "
            result = model.infer(
                tokenizer,
                prompt=prompt,
                image_file=temp_img_path,
                base_size=1024,
                image_size=640,
                crop_mode=True
            )

            if result:
                return str(result).strip()
        except Exception:  # noqa: BLE001
            pass  # Fall back to Tesseract
        finally:
            if temp_img_path and os.path.exists(temp_img_path):
                os.remove(temp_img_path)

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

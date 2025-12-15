"""
PDF processing utilities for text extraction and OCR.
"""

import tempfile
import os
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


def extract_text_from_pdf(file: Union[BinaryIO, bytes]) -> str:
    """
    Extract text from a PDF file using various methods.
    
    Args:
        file: Binary file object (uploaded PDF) or raw bytes
        
    Returns:
        str: Extracted text content
    """
    # Obtain PDF bytes robustly (handles Streamlit UploadedFile)
    pdf_bytes: Optional[bytes] = None
    try:
        if isinstance(file, (bytes, bytearray)):
            pdf_bytes = bytes(file)
        elif hasattr(file, "getvalue") and callable(getattr(file, "getvalue")):
            pdf_bytes = file.getvalue()
        elif hasattr(file, "read") and callable(getattr(file, "read")):
            try:
                if hasattr(file, "seek") and callable(getattr(file, "seek")):
                    file.seek(0)
            except Exception:
                pass
            pdf_bytes = file.read()
    except Exception as e:
        return f"[PDF Read Error: {e}]"

    if not pdf_bytes:
        return "[PDF Error: Empty upload]"
    

    # Save uploaded bytes to a temporary file
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        tmp.write(pdf_bytes)
        tmp_path = tmp.name

    try:
        # Try native text extraction first (default)
        doc = fitz.open(tmp_path)
        full_text = ""
        for page in doc:
            full_text += page.get_text()
        doc.close()
        
        # If no text was extracted, fallback to OCR
        if not full_text.strip():
            full_text = _extract_text_with_ocr(tmp_path)
    
    finally:
        # Clean up temp file
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

    return full_text


def _extract_text_with_ocr(pdf_path: str) -> str:
    """
    Extract text using OCR when native extraction fails.
    Tries DeepSeek-OCR first (if available), falls back to Tesseract.
    Uses higher DPI (300) for better scanned document quality.
    
    Args:
        pdf_path: Path to the PDF file
        
    Returns:
        str: OCR extracted text
    """
    doc = None    
    try:
        doc = fitz.open(pdf_path)
        ocr_text = ""

        for page_num, page in enumerate(doc, 1):
            # Render at high DPI (300) for scanned documents
            mat = fitz.Matrix(300/72, 300/72)  # 300 DPI
            pix = page.get_pixmap(matrix=mat)
            image = Image.open(BytesIO(pix.tobytes("png")))
            
            page_text = ""
            
            # Try DeepSeek-OCR via transformers first (if available)
            if _transformers_available:
                try:
                    global _deepseek_model, _deepseek_tokenizer
                    if _deepseek_model is None:
                        _deepseek_tokenizer = AutoTokenizer.from_pretrained("deepseek-ai/DeepSeek-OCR", trust_remote_code=True)
                        _deepseek_model = AutoModel.from_pretrained(
                            "deepseek-ai/DeepSeek-OCR",
                            trust_remote_code=True,
                            use_safetensors=True,
                            device_map="auto"  # Auto-detect GPU/CPU
                        )
                        _deepseek_model = _deepseek_model.eval()
                    
                    # Save image temporarily for model.infer
                    temp_img_path = os.path.join(tempfile.gettempdir(), f"temp_page_{page_num}.png")
                    image.save(temp_img_path)
                    
                    prompt = "<image>\n<|grounding|>Convert the document to markdown. "
                    result = _deepseek_model.infer(
                        _deepseek_tokenizer,
                        prompt=prompt,
                        image_file=temp_img_path,
                        base_size=1024,
                        image_size=640,
                        crop_mode=True
                    )
                    
                    if result:
                        page_text = str(result).strip()
                        if page_text:
                            ocr_text += page_text + "\n"
                            if os.path.exists(temp_img_path):
                                os.remove(temp_img_path)
                            continue
                    
                    if os.path.exists(temp_img_path):
                        os.remove(temp_img_path)
                except Exception as ds_err:  # noqa: BLE001
                    pass  # Fall back to Tesseract

            # Fall back to Tesseract
            try:
                page_text = pytesseract.image_to_string(image).strip()
                if page_text:
                    ocr_text += page_text + "\n"
            except Exception:  # noqa: BLE001
                pass  # Skip page if both fail

        return ocr_text if ocr_text.strip() else "[OCR Error: No text extracted from any page]"
    except Exception as ocr_err:  # noqa: BLE001
        return f"[OCR Error: {ocr_err}]"
    finally:
        if doc is not None:
            doc.close()

def get_text_length_info(text: str) -> dict:
    """
    Get information about text length for processing decisions.
    
    Args:
        text: Input text
        
    Returns:
        dict: Text length information
    """
    length = len(text)
    return {
        "length": length,
        "is_short": length < 3000,
        "recommended_truncate": min(3500, length) if length >= 3000 else length
    }
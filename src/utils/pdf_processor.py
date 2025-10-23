"""
PDF processing utilities for text extraction and OCR.
"""

import tempfile
import os
import fitz  # PyMuPDF
import pytesseract
from pdf2image import convert_from_path
from typing import BinaryIO


def extract_text_from_pdf(file: BinaryIO) -> str:
    """
    Extract text from a PDF file using PyMuPDF and OCR fallback.
    
    Args:
        file: Binary file object (uploaded PDF)
        
    Returns:
        str: Extracted text content
    """
    # Save uploaded file to a temporary file
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        tmp.write(file.read())
        tmp_path = tmp.name

    try:
        # Try native text extraction first
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
    
    Args:
        pdf_path: Path to the PDF file
        
    Returns:
        str: OCR extracted text
    """
    try:
        images = convert_from_path(pdf_path)
        ocr_text = ""
        for image in images:
            ocr_text += pytesseract.image_to_string(image) + "\n"
        return ocr_text
    except Exception as ocr_err:
        return f"\n[OCR Error: {ocr_err}]"


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
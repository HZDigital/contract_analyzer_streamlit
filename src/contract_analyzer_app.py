import streamlit as st
import fitz  # PyMuPDF
from openai import AzureOpenAI
import tempfile
import os
import pytesseract
from pdf2image import convert_from_path
from PIL import Image
import time

# ===========================
# Azure OpenAI Configuration
# ===========================
# Get API key and endpoint from environment variables or use defaults
api_key = os.environ.get("AZURE_OPENAI_API_KEY")
azure_endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT")

client = AzureOpenAI(
    api_key=api_key,
    api_version="2024-12-01-preview",
    azure_endpoint=azure_endpoint
)
deployment_name = "gpt-4o-mini"

# ===========================
# Streamlit App Configuration
# ===========================
st.set_page_config(page_title="Contract Analyzer", layout="wide")
st.title("📄 Contract Analyzer (Local LLM + OCR)")

st.markdown("""
Upload one or more PDF contracts.  
The app will extract text and analyze each document for:
- 📌 Summary  
- 📌 Key Clauses (e.g. Termination, Confidentiality, Payment)  
- ⚠️ Risky or unusual language
""")

uploaded_files = st.file_uploader("Upload contract PDFs", type=["pdf"], accept_multiple_files=True)

def extract_text_from_pdf(file):
    import os

    # Save uploaded file to a real temp file path and close it
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        tmp.write(file.read())
        tmp_path = tmp.name

    # Try native text extraction first
    doc = fitz.open(tmp_path)
    full_text = ""
    for page in doc:
        full_text += page.get_text()
    doc.close()

    # If no text was extracted, fallback to OCR
    if not full_text.strip():
        try:
            # In Docker, poppler is installed in the system path
            images = convert_from_path(tmp_path)
            for image in images:
                full_text += pytesseract.image_to_string(image) + "\n"
        except Exception as ocr_err:
            full_text += f"\n[OCR Error: {ocr_err}]"

    # Optionally clean up temp file
    os.remove(tmp_path)

    return full_text

def save_analysis_result(file_name, content):
    folder = "results"
    os.makedirs(folder, exist_ok=True)
    full_path = os.path.join(folder, f"result_{file_name}.txt")
    with open(full_path, "w", encoding="utf-8") as f:
        f.write(content)

def analyze_contract(text, truncate_length):
    prompt = f"""
You are a legal assistant. Analyze the following contract and provide:

1. A brief summary of what the contract is about.
2. Extract and list important clauses like:
   - Termination
   - Confidentiality
   - Payment terms
   - Liabilities
   For each clause, include a direct quote from the contract text where the clause is mentioned.
3. Identify and list any unusual, risky, or concerning parts, and for each include a direct quote from the contract text.
4. Extract the contract's start date and terminal (termination) date if they are mentioned.

Contract Text:
{text[:truncate_length]}  # Truncate for token limits
    """
    
    response = client.chat.completions.create(
        model=deployment_name,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.choices[0].message.content.strip()

if uploaded_files:
    # Convert to list to support reversing and indexing
    files_list = list(uploaded_files)
    
    # Store analysis results to display them later in reverse order
    analysis_results = []
    
    # Process each file and store results
    for i, file in enumerate(files_list):
        result = {
            "file_name": file.name,
            "analysis": None,
            "success": False,
            "error": None
        }
        
        try:
            # Create status placeholders for each step
            status_extraction = st.empty()
            status_ocr = st.empty()
            status_analysis = st.empty()
            status_saving = st.empty()
            
            # Step 1: Extract text
            with status_extraction:
                with st.spinner("Extracting text from document..."):
                    # Save uploaded file to a real temp file path and close it
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                        tmp.write(file.read())
                        tmp_path = tmp.name

                    # Try native text extraction first
                    doc = fitz.open(tmp_path)
                    raw_text = ""
                    for page in doc:
                        raw_text += page.get_text()
                    doc.close()
            
            # Update extraction status and clear after delay
            status_extraction.success("✅ Text extraction complete")
            time.sleep(3)
            status_extraction.empty()
            
            # Step 2: OCR if needed
            if not raw_text.strip():
                with status_ocr:
                    with st.spinner("No text found. Applying OCR to scan document..."):
                        try:
                            images = convert_from_path(tmp_path)
                            for image in images:
                                raw_text += pytesseract.image_to_string(image) + "\n"
                            status_ocr.success("✅ OCR processing complete")
                            time.sleep(3)
                            status_ocr.empty()
                        except Exception as ocr_err:
                            raw_text += f"\n[OCR Error: {ocr_err}]"
                            status_ocr.error(f"❌ OCR failed: {str(ocr_err)}")
                            time.sleep(3)
                            status_ocr.empty()
            
            # Clean up temp file
            os.remove(tmp_path)
            
            if len(raw_text.strip()) == 0:
                result["error"] = "No readable text found in this file."
                analysis_results.append(result)
                continue

            text_length = len(raw_text)
            # If the document is shorter than 3000 characters, use the full text for analysis
            if text_length < 3000:
                truncate_length = text_length
                st.info("Document is shorter than 3000 characters; using full text for analysis.")
            else:
                truncate_length = st.slider(
                    f"Select contract text length for analysis for `{file.name}`",
                    min_value=3000,
                    max_value=text_length,
                    value=min(3500, text_length),
                    step=500
                )
            
            # Step 3: Analyze with Azure OpenAI
            with status_analysis:
                with st.spinner("Analyzing contract with LLM..."):
                    analysis = analyze_contract(raw_text, truncate_length)
            status_analysis.success("✅ AI analysis complete")
            time.sleep(3)
            status_analysis.empty()
            
            # Step 4: Save results
            with status_saving:
                with st.spinner("Saving analysis results..."):
                    save_analysis_result(file.name, analysis)
            status_saving.success("✅ Results saved to file")
            time.sleep(3)
            status_saving.empty()
            
            # Store successful analysis
            result["analysis"] = analysis
            result["success"] = True
            
        except Exception as e:
            result["error"] = str(e)
        
        analysis_results.append(result)
    
    # Display results in reverse order (most recent first)
    for i, result in enumerate(reversed(analysis_results)):
        # Only expand the most recent result
        is_expanded = (i == 0)
        
        with st.expander(f"🔍 Analyzed: `{result['file_name']}`", expanded=is_expanded):
            if result["success"]:
                st.markdown("### 📊 Analysis Results")
                st.markdown(result["analysis"])
            else:
                st.error(f"Failed to analyze {result['file_name']}: {result['error']}")

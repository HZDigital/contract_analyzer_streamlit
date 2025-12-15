"""
Use Case 3 - Comparison of factory test certificates against specifications.

This page lets users:
- Upload all PDFs (specifications and certificates) together
- AI automatically identifies which are specs vs certificates
- AI extracts parameters and performs intelligent comparison
- Displays comparison results with tolerance checks
- Export results to CSV
"""

from __future__ import annotations

import json
from typing import Dict, Any

import pandas as pd
import streamlit as st

from utils.pdf_processor import extract_text_from_pdf


# --------------
# Page rendering
# --------------


def render_factory_test_comparison_page():
    
    st.title("Factory Certificate Comparison")
    st.markdown(
        """
        **Simple AI-powered certificate comparison:**
        - Drop all your PDFs (specifications and certificates) in one upload
        - AI will automatically identify specs vs certificates
        - Get instant comparison table with tolerance analysis
        """
    )

    st.markdown("---")

    # Single file uploader for all PDFs
    uploaded_files = st.file_uploader(
        "Upload all PDFs (specifications and certificates)",
        type=["pdf"],
        accept_multiple_files=True,
        key="all_pdfs_upload",
        help="Drop both specification PDFs and certificate PDFs here - AI will figure out which is which",
    )

    if not uploaded_files:
        st.info("Upload your specification and certificate PDFs to begin automatic comparison.")
        return

    if len(uploaded_files) < 2:
        st.warning("Please upload at least 2 PDFs (at least one specification and one certificate).")
        return

    if st.button("🚀 Analyze & Compare", type="primary", use_container_width=True):
        _process_ai_comparison(uploaded_files )


def _process_ai_comparison(uploaded_files):
    """Process all PDFs and let AI do the identification and comparison."""
    progress = st.progress(0)
    status = st.empty()
    
    # Step 1: Extract text from all PDFs
    status.text("Extracting text from all PDFs...")
    file_texts = {}
    
    for idx, file in enumerate(uploaded_files):
        try:
            text = extract_text_from_pdf(file)
            file_texts[file.name] = text
            progress.progress((idx + 1) / (len(uploaded_files) + 1))
        except Exception as e:
            st.error(f"Failed to extract text from {file.name}: {e}")
            continue
    
    if len(file_texts) < 2:
        st.error("Could not extract text from enough files. Need at least 2 readable PDFs.")
        return
    
    # Step 2: Send all to AI for intelligent comparison
    status.text("AI analyzing and comparing all documents...")
    comparison_result = _ai_smart_compare(file_texts)
    progress.progress(1.0)
    
    if comparison_result.get("error"):
        st.error(f"AI comparison failed: {comparison_result['error']}")
        return
    
    status.text("Analysis complete! ✅")
    
    # Display results
    _display_smart_comparison_results(comparison_result)


def _ai_smart_compare(file_texts: Dict[str, str]) -> Dict[str, Any]:
    """Let AI identify specs vs certificates and perform comparison."""
    from config.settings import azure_config
    
    if not azure_config.client:
        return {"error": "Azure OpenAI not configured"}
    
    # Build context with all files
    files_context = ""
    for idx, (filename, text) in enumerate(file_texts.items(), 1):
        files_context += f"\n\n=== DOCUMENT {idx}: {filename} ===\n{text[:8000]}\n"  # Limit each doc
    
    prompt = f"""
You are analyzing multiple technical documents. Your task:

1. **IDENTIFY** which documents are specifications vs certificates/test reports
2. **EXTRACT** all parameters from specifications (with tolerances, min/max, nominal values)
3. **EXTRACT** all measured values from certificates
4. **COMPARE** measured values against specification tolerances
5. **RETURN** a complete comparison table

Documents to analyze:
{files_context}

Return ONLY valid JSON with this structure:
{{
  "identified_specs": ["list of spec filenames"],
  "identified_certificates": ["list of certificate filenames"],
  "comparisons": [
    {{
      "parameter": "parameter name",
      "unit": "unit of measurement",
      "spec_min": number or null,
      "spec_max": number or null,
      "spec_nominal": number or null,
      "measured_value": number or null,
      "measured_from": "certificate filename",
      "status": "OK" | "OUT" | "MISSING" | "NO_SPEC",
      "deviation": "description of deviation if OUT"
    }}
  ],
  "summary": "Brief summary of comparison results"
}}

Status definitions:
- OK: Measured value within specification tolerances
- OUT: Measured value outside tolerances
- MISSING: Parameter in spec but no measurement found
- NO_SPEC: Measurement found but no specification for it

DO NOT use markdown. Return raw JSON only.
"""
    
    try:
        response = azure_config.client.chat.completions.create(
            model=azure_config.deployment_name,
            messages=[{"role": "user", "content": prompt}],
        )
        response_text = response.choices[0].message.content.strip()
        
        # Clean markdown if present
        if "```json" in response_text:
            response_text = response_text.split("```json")[1].split("```")[0].strip()
        elif "```" in response_text:
            response_text = response_text.split("```")[1].split("```")[0].strip()
        
        data = json.loads(response_text)
        return data
    except Exception as e:
        return {"error": str(e)}


def _display_smart_comparison_results(result: Dict[str, Any]):
    """Display the AI comparison results."""
    st.markdown("## 📊 Analysis Results")
    
    # Show document identification
    with st.expander("🔍 Document Identification", expanded=False):
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("**Specifications:**")
            for spec in result.get("identified_specs", []):
                st.write(f"• {spec}")
        with col2:
            st.markdown("**Certificates:**")
            for cert in result.get("identified_certificates", []):
                st.write(f"• {cert}")
    
    # Summary
    if result.get("summary"):
        st.info(f"**Summary:** {result['summary']}")
    
    # Comparison table
    comparisons = result.get("comparisons", [])
    if not comparisons:
        st.warning("No comparisons found.")
        return
    
    df = pd.DataFrame(comparisons)
    
    # Calculate metrics
    ok_count = (df["status"].str.upper() == "OK").sum()
    out_count = (df["status"].str.upper() == "OUT").sum()
    missing_count = (df["status"].str.upper() == "MISSING").sum()
    
    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("Within Tolerance", int(ok_count))
    with c2:
        st.metric("Out of Tolerance", int(out_count))
    with c3:
        st.metric("Missing Measurements", int(missing_count))
    
    st.markdown("---")
    st.markdown("### 📋 Comparison Table")
    
    # Color coding - using colors that work in both light and dark mode
    def highlight_row(row):
        status = str(row.get("status", "")).upper()
        if status == "OUT":
            return ["background-color: rgba(220, 53, 69, 0.3); border-left: 3px solid #dc3545"] * len(row)
        if status == "MISSING":
            return ["background-color: rgba(255, 193, 7, 0.3); border-left: 3px solid #ffc107"] * len(row)
        if status == "OK":
            return ["background-color: rgba(40, 167, 69, 0.3); border-left: 3px solid #28a745"] * len(row)
        return [""] * len(row)
    
    styled = df.style.apply(highlight_row, axis=1)
    st.dataframe(styled, use_container_width=True, hide_index=True)
    
    # Export
    st.markdown("### 📥 Export Results")
    csv_bytes = df.to_csv(index=False, sep=";").encode("utf-8")
    st.download_button(
        label="Download Comparison CSV",
        data=csv_bytes,
        file_name="certificate_comparison.csv",
        mime="text/csv",
    )

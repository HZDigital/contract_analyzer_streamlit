"""
Detailed analysis page for individual contract processing.
"""

import streamlit as st
import pandas as pd
import time
from utils.pdf_processor import extract_text_from_pdf, get_text_length_info
from utils.ai_analyzer import analyze_contract
from utils.file_utils import save_analysis_result, generate_detailed_analysis_csv


def render_detailed_analysis_page():
    """Render the detailed contract analysis page."""
    # Back button
    col1, col2 = st.columns([1, 3])
    with col1:
        if st.button("← Back to Dashboard", width="stretch"):
            st.session_state.current_page = "dashboard"
            st.rerun()
    
    st.title("Detailed Contract Analysis")
    
    st.markdown("""
    Upload one or more PDF contracts for detailed analysis.  
    The app will extract text and analyze each document for:
    - 📌 Summary  
    - 📌 Key Clauses (e.g. Termination, Confidentiality, Payment)  
    - ⚠️ Risky or unusual language
    """)
    
    uploaded_files = st.file_uploader(
        "Upload contract PDFs for detailed analysis", 
        type=["pdf"], 
        accept_multiple_files=True
    )
    
    if uploaded_files:
        _process_detailed_analysis(uploaded_files)


def _process_detailed_analysis(uploaded_files):
    """Process files for detailed analysis."""
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
            result = _analyze_single_file(file, result)
        except Exception as e:
            result["error"] = str(e)
        
        analysis_results.append(result)
    
    # Display results in reverse order (most recent first)
    _display_analysis_results(analysis_results)


def _analyze_single_file(file, result):
    """Analyze a single file with progress tracking."""
    # Create status placeholders for each step
    status_extraction = st.empty()
    status_ocr = st.empty()
    status_analysis = st.empty()
    status_saving = st.empty()
    
    # Step 1: Extract text
    with status_extraction:
        with st.spinner("Extracting text from document..."):
            raw_text = extract_text_from_pdf(file)
    
    # Update extraction status and clear after delay
    status_extraction.success("✅ Text extraction complete")
    time.sleep(2)
    status_extraction.empty()
    
    if len(raw_text.strip()) == 0:
        result["error"] = "No readable text found in this file."
        return result
    
    # Get text length information
    text_info = get_text_length_info(raw_text)
    
    # Handle text length and truncation
    if text_info["is_short"]:
        truncate_length = text_info["length"]
        st.info("Document is shorter than 3000 characters; using full text for analysis.")
    else:
        truncate_length = st.slider(
            f"Select contract text length for analysis for `{file.name}`",
            min_value=3000,
            max_value=text_info["length"],
            value=text_info["recommended_truncate"],
            step=500
        )
    
    # Step 2: Analyze with Azure OpenAI
    with status_analysis:
        with st.spinner("Analyzing contract with AI..."):
            analysis = analyze_contract(raw_text, truncate_length)

    status_analysis.success("✅ AI analysis complete")
    time.sleep(2)
    status_analysis.empty()

    # Step 3: Save results
    with status_saving:
        with st.spinner("Saving analysis results..."):
            # Serialize analysis to JSON string if it's a dict
            import json
            analysis_to_save = json.dumps(analysis, indent=2, ensure_ascii=False) if isinstance(analysis, dict) else str(analysis)
            save_analysis_result(file.name, analysis_to_save)

    status_saving.success("✅ Results saved to file")
    time.sleep(2)
    status_saving.empty()

    # Store successful analysis
    result["analysis"] = analysis
    result["success"] = True

    return result


def _display_analysis_results(analysis_results):
    """Display the analysis results."""
    # Add CSV export button at the top if there are results
    if analysis_results and any(result.get("success", False) for result in analysis_results):
        st.markdown("### 📊 Export Options")
        csv_data = generate_detailed_analysis_csv(analysis_results)
        st.download_button(
            label="📥 Download Complete Analysis as CSV",
            data=csv_data,
            file_name=f"detailed_analysis_{time.strftime('%Y%m%d_%H%M%S')}.csv",
            mime="text/csv"
        )
        st.markdown("---")
    
    for i, result in enumerate(reversed(analysis_results)):
        # Only expand the most recent result
        is_expanded = (i == 0)
        
        with st.expander(f"🔍 Analyzed: `{result['file_name']}`", expanded=is_expanded):
            if result["success"]:
                _display_structured_analysis(result["analysis"])
            else:
                st.error(f"Failed to analyze {result['file_name']}: {result['error']}")


def _display_structured_analysis(analysis):
    """Display structured analysis results with tables."""
    # Handle error case
    if isinstance(analysis, str) or "error" in analysis:
        st.error("Analysis failed or returned unstructured data")
        if isinstance(analysis, str):
            st.markdown(analysis)
        else:
            st.error(analysis.get("error", "Unknown error"))
        return
    
    # Basic Information
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**Client/Customer:**")
        st.write(analysis.get("client_name", "Not specified"))
        
        st.markdown("**Contract Type:**")
        st.write(analysis.get("contract_type", "Not specified"))
    
    with col2:
        st.markdown("**Start Date:**")
        st.write(analysis.get("start_date", "Not specified"))
        
        st.markdown("**End Date:**")
        st.write(analysis.get("end_date", "Not specified"))
    
    # Summary
    st.markdown("### 📋 Contract Summary")
    st.write(analysis.get("summary", "Summary not available"))
    
    # Products/Services Table
    st.markdown("### 🛍️ Products & Services")
    products_services = analysis.get("products_services", [])
    
    if products_services:
        # Create DataFrame for products/services
        df_products = pd.DataFrame(products_services)
        
        # Ensure all expected columns exist
        expected_columns = ["name", "description", "quantity", "unit", "rate"]
        for col in expected_columns:
            if col not in df_products.columns:
                df_products[col] = "Not specified"
        
        # Display as table
        st.dataframe(
            df_products[expected_columns],
            column_config={
                "name": "Product/Service",
                "description": "Description",
                "quantity": "Quantity",
                "unit": "Unit",
                "rate": "Rate/Price"
            },
            width="stretch"
        )
        
        # CSV Export button for products/services
        csv_data = df_products.to_csv(index=False, sep=";").encode("utf-8")
        st.download_button(
            label="📥 Download Products/Services as CSV",
            data=csv_data,
            file_name="products_services.csv",
            mime="text/csv"
        )
    else:
        st.info("No products or services extracted from this contract.")
    
    # Key Clauses
    st.markdown("### 📝 Key Clauses")
    key_clauses = analysis.get("key_clauses", [])
    
    if key_clauses:
        for clause in key_clauses:
            with st.expander(f"**{clause.get('type', 'Unknown Clause')}**"):
                st.write(f"**Description:** {clause.get('description', 'No description')}")
                st.markdown(f"**Quote:** _{clause.get('quote', 'No quote available')}_")
    else:
        st.info("No key clauses extracted from this contract.")
    
    # Risk Areas
    st.markdown("### ⚠️ Risk Areas & Concerns")
    risk_areas = analysis.get("risk_areas", [])
    
    if risk_areas:
        for risk in risk_areas:
            st.warning(f"**{risk.get('concern', 'Unknown concern')}**")
            st.markdown(f"_{risk.get('quote', 'No quote available')}_")
            st.markdown("---")
    else:
        st.success("No significant risk areas identified in this contract.")
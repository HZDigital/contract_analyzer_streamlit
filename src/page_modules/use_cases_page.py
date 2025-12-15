"""
Unified Use Cases Page - Select and execute different AI analysis use cases.

This page provides access to:
- Use Case 1: Tender Document Analysis
- Use Case 2: Contract Review of Cooperation Agreements
- Use Case 3: Factory Certificate Comparison
"""

import streamlit as st


def render_use_cases_page():
    """Main use cases page with selector."""
    
    # Back button
    col1, col2 = st.columns([1, 3])
    with col1:
        if st.button("← Back to Dashboard", use_container_width=True):
            st.session_state.current_page = "dashboard"
            st.rerun()
    
    st.title("AI Contract Analysis - Use Cases")
    st.markdown(
        """
        Select a use case below to begin your analysis:
        """
    )
    
    st.markdown("---")
    
    # Use case selector
    use_case = st.radio(
        "**Choose your analysis type:**",
        [
            "Use Case 1: Tender Document Analysis",
            "Use Case 2: Contract Review - Cooperation Agreements",
            "Use Case 3: Factory Certificate Comparison"
        ],
        key="use_case_selector",
        help="Select the type of analysis you want to perform"
    )
    
    st.markdown("---")
    
    # Route to the appropriate use case
    if "Use Case 1" in use_case:
        _render_tender_analysis()
    elif "Use Case 2" in use_case:
        _render_contract_review()
    elif "Use Case 3" in use_case:
        _render_factory_test_comparison()


def _render_tender_analysis():
    """Use Case 1 - Analyzing tender documents & fill out internal tender list."""
    st.header("📋 Use Case 1: Tender Document Analysis")
    st.markdown(
        """
        **AI-powered tender document analysis:**
        - Upload tender documents (PDFs)
        - AI extracts key information automatically
        - Generate internal tender list
        - Export structured data
        """
    )

    st.markdown("---")

    # Not implemented message
    st.info("🚧 This feature is not implemented yet.")
    
    st.markdown(
        """
        ### Planned Features:
        - 📄 Upload multiple tender documents
        - 🤖 AI extraction of key tender information
        - 📊 Auto-fill internal tender list template
        - 💾 Export to Excel/CSV format
        - 🔍 Compare multiple tenders side-by-side
        
        Stay tuned for updates!
        """
    )


def _render_contract_review():
    """Use Case 2 - Contract review of cooperation agreements."""
    st.header("📝 Use Case 2: Contract Review - Cooperation Agreements")
    st.markdown(
        """
        **AI-powered contract review:**
        - Upload cooperation agreements (PDFs)
        - AI analyzes contract terms and clauses
        - Identifies risks and obligations
        - Generates comprehensive review report
        """
    )

    st.markdown("---")

    # Not implemented message
    st.info("🚧 This feature is not implemented yet.")
    
    st.markdown(
        """
        ### Planned Features:
        - 📄 Upload cooperation agreements
        - 🤖 AI-powered clause analysis
        - ⚠️ Risk identification and flagging
        - 📋 Extract key obligations and deadlines
        - 🔐 Confidentiality and liability assessment
        - 📊 Generate review summary report
        - 💾 Export findings to Word/PDF
        
        Stay tuned for updates!
        """
    )


def _render_factory_test_comparison():
    """Use Case 3 - Comparison of factory test certificates against specifications."""
    from page_modules.factory_test_comparison import render_factory_test_comparison_page
    
    render_factory_test_comparison_page()

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
        if st.button("← Back to Dashboard", width="stretch"):
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
        from page_modules.tender_analysis import render_tender_analysis_page
        render_tender_analysis_page()
    elif "Use Case 2" in use_case:
        from page_modules.contract_review_cooperation import render_contract_review_cooperation_page
        render_contract_review_cooperation_page()
    elif "Use Case 3" in use_case:
        _render_factory_test_comparison()


def _render_factory_test_comparison():
    """Use Case 3 - Comparison of factory test certificates against specifications."""
    from page_modules.factory_test_comparison import render_factory_test_comparison_page
    
    render_factory_test_comparison_page()

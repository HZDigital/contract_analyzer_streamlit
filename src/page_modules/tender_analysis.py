"""
Use Case 1 - Analyzing tender documents & fill out internal tender list.

This page lets users:
- Upload tender documents
- AI automatically extracts key information
- Fills out internal tender list template
- Export results
"""

import streamlit as st


def render_tender_analysis_page():
    st.title("Tender Document Analysis")
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

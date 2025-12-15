"""
Contract Analyzer - Main Streamlit Application
A multi-page application for analyzing PDF contracts with AI.
"""

import streamlit as st
import sys
import os

# Add src directory to Python path for imports
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from config.settings import azure_config
from page_modules.bulk_upload import render_bulk_upload_page
from page_modules.detailed_analysis import render_detailed_analysis_page
from page_modules.invoice_upload import render_invoice_upload_page
from page_modules.use_cases_page import render_use_cases_page


def main():
    """Main application function."""
    # Configure Streamlit page
    st.set_page_config(
        page_title="Contract Analyzer", 
        layout="wide", 
        initial_sidebar_state="expanded"
    )
    
    # Sidebar Navigation
    st.sidebar.title("Navigation")
    page = st.sidebar.radio(
        "Select Page", 
        [
            "Product Request Detection",
            "Invoice Request Detection",
            "Detailed Contract Analysis",
            "Miller Cases",
        ],
        key="main_navigation"  # Add unique key to fix duplicate element error
    )
    
    # Show credentials warning if needed
    azure_config.show_credentials_warning()
    
    # Route to appropriate page
    if page == "Product Request Detection":
        render_bulk_upload_page()
    elif page == "Invoice Request Detection":
        render_invoice_upload_page()
    elif page == "Detailed Contract Analysis":
        render_detailed_analysis_page()
    elif page == "Miller Cases":
        render_use_cases_page()


if __name__ == "__main__":
    main()
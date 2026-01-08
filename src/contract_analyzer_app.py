"""
Contract Analyzer - Main Streamlit Application
A multi-page application for analyzing PDF contracts with AI.
"""

import streamlit as st
import sys
import os

# Add src directory to Python path for imports
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from config.settings import azure_config, app_config
from page_modules.dashboard_home import render_dashboard_home
from page_modules.bulk_upload import render_bulk_upload_page
from page_modules.detailed_analysis import render_detailed_analysis_page
from page_modules.invoice_upload import render_invoice_upload_page
from page_modules.use_cases_page import render_use_cases_page


def main():
    """Main application function."""
    # Configure Streamlit page - hide sidebar completely
    st.set_page_config(
        page_title="Contract Analyzer", 
        layout="wide", 
        initial_sidebar_state="collapsed"
    )
    
    # Hide sidebar completely with CSS
    st.markdown(
        """
        <style>
        [data-testid="stSidebar"] {
            display: none;
        }
        </style>
        """,
        unsafe_allow_html=True
    )
    
    # Show credentials warning if needed
    azure_config.show_credentials_warning()
    
    # Initialize session state for page navigation
    if "current_page" not in st.session_state:
        st.session_state.current_page = "dashboard"
    
    # Get available pages based on environment
    available_pages = app_config.get_available_pages()
    
    # Check if current page is allowed, redirect to dashboard if not
    if st.session_state.current_page not in available_pages:
        st.session_state.current_page = "dashboard"
        st.rerun()
    
    # Route to appropriate page based on session state
    if st.session_state.current_page == "dashboard":
        render_dashboard_home()
    elif st.session_state.current_page == "product_detection" and "product_detection" in available_pages:
        render_bulk_upload_page()
    elif st.session_state.current_page == "invoice_detection" and "invoice_detection" in available_pages:
        render_invoice_upload_page()
    elif st.session_state.current_page == "detailed_analysis" and "detailed_analysis" in available_pages:
        render_detailed_analysis_page()
    elif st.session_state.current_page == "mehler_cases"  and "mehler_cases" in available_pages:
        render_use_cases_page()


if __name__ == "__main__":
    main()
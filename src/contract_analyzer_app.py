"""
Contract Analyzer - Main Streamlit Application
A multi-page application for analyzing PDF contracts with AI.
"""

import streamlit as st
import sys
import os
import requests

# Add src directory to Python path for imports
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from config.settings import azure_config, app_config
from config.msal_config import msal_config
from page_modules.dashboard_home import render_dashboard_home
from page_modules.bulk_upload import render_bulk_upload_page
from page_modules.detailed_analysis import render_detailed_analysis_page
from page_modules.invoice_upload import render_invoice_upload_page
from page_modules.use_cases_page import render_use_cases_page

def validate_token_from_parent(token: str) -> bool:
    """Validate access token from parent React application."""
    try:
        headers = {"Authorization": f"Bearer {token}"}
        response = requests.get(
            "https://graph.microsoft.com/v1.0/me",
            headers=headers,
            timeout=5
        )
        
        if response.status_code == 200:
            user_info = response.json()
            # Store user information in session
            st.session_state.auth_user = {
                "name": user_info.get("displayName"),
                "email": user_info.get("mail") or user_info.get("userPrincipalName"),
                "id": user_info.get("id"),
                "from_parent": True  # Track that user came from parent app
            }
            return True
        return False
    except Exception as e:
        st.error(f"Token validation error: {e}")
        return False


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
    
    # Check if authentication is disabled
    auth_disabled = os.environ.get("AUTH_DISABLED", "false").lower() == "true"
    
    # Initialize MSAL config session
    msal_config.initialize_session()
    
    # Handle token from parent React application (iframe scenario)
    query_params = st.query_params
    if "token" in query_params and not st.session_state.auth_user:
        token = query_params["token"]
        
        if validate_token_from_parent(token):
            # Clear token from URL for security
            st.query_params.clear()
            st.rerun()
        else:
            st.error("Invalid or expired token. Please try again.")
            st.stop()
    
    # Handle OAuth callback from Microsoft
    if "code" in query_params and not auth_disabled:
        msal_config.handle_callback()
    
    # Check if authentication is required and user is not authenticated
    if not auth_disabled and not msal_config.is_authenticated():
        # Show login page
        msal_config.render_login_page()
        st.stop()
    
    # Show credentials warning if needed
    azure_config.show_credentials_warning()
    
    # Show user info and render user menu
    msal_config.render_user_menu()
    
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
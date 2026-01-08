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
from page_modules.dashboard_home import render_dashboard_home
from page_modules.bulk_upload import render_bulk_upload_page
from page_modules.detailed_analysis import render_detailed_analysis_page
from page_modules.invoice_upload import render_invoice_upload_page
from page_modules.use_cases_page import render_use_cases_page


def is_auth_configured() -> bool:
    """Check if Streamlit auth provider is configured in secrets.toml."""
    try:
        auth = st.secrets["auth"]
        redirect_uri = auth.get("redirect_uri")
        cookie_secret = auth.get("cookie_secret")
        provider = auth.get("microsoft", {})
        client_id = provider.get("client_id")
        client_secret = provider.get("client_secret")
        metadata_url = provider.get("server_metadata_url")
        return bool(redirect_uri and cookie_secret and client_id and client_secret and metadata_url)
    except Exception:
        return False

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
    
    # Initialize session state
    if "auth_user" not in st.session_state:
        st.session_state.auth_user = None
    
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
    

    

    # Check if user is logged in via Streamlit's built-in auth
    is_streamlit_logged_in = False
    try:
        is_streamlit_logged_in = st.user.is_logged_in
    except AttributeError:
        # st.user.is_logged_in not available (older Streamlit version or auth not configured)
        pass
    
    # Handle authentication for direct users
    if not auth_disabled and not st.session_state.auth_user and not is_streamlit_logged_in:
        # Show login page for direct access
        st.markdown(
            """
            <div style="text-align: center; margin: 100px 0;">
                <h1 style="color: #FF6B6B;">Contract Analyzer</h1>
                <p style="font-size: 1.2em; color: #666;">Please log in to continue</p>
            </div>
            """,
            unsafe_allow_html=True
        )
        
        col1, col2, col3 = st.columns([1, 1, 1])
        with col2:
            if is_auth_configured():
                # Only render login button if Streamlit auth is available
                try:
                    st.button(
                        "🔐 Login with Microsoft", 
                        on_click=st.login, 
                        args=["microsoft"],
                        use_container_width=True, 
                        type="primary"
                    )
                except AttributeError:
                    st.error(
                        "⚠️ Your Streamlit version may not support built-in auth.\n"
                        "Please upgrade Streamlit to the latest version."
                    )
            else:
                st.error(
                    "⚠️ Authentication provider not configured.\n\n"
                    "Ensure `.streamlit/secrets.toml` contains [auth] and [auth.microsoft] with `redirect_uri`, `cookie_secret`,\n"
                    "`client_id`, `client_secret`, and `server_metadata_url`."
                )
        st.stop()
    
    # Handle Streamlit's built-in login for direct users
    if is_streamlit_logged_in and not st.session_state.auth_user:
        try:
            st.session_state.auth_user = {
                "name": st.user.name,
                "email": st.user.email,
                "from_parent": False
            }
        except AttributeError:
            pass
    
    # Show credentials warning if needed
    azure_config.show_credentials_warning()
    
    # Show user info if logged in
    if st.session_state.auth_user:
        with st.sidebar:
            st.markdown("---")
            st.markdown(f"**User:** {st.session_state.auth_user.get('name', 'Unknown')}")
            st.markdown(f"**Email:** {st.session_state.auth_user.get('email', 'N/A')}")
            
            # Only show logout for direct users (not from parent)
            if not st.session_state.auth_user.get("from_parent"):
                if st.button("Logout", key="logout_btn"):
                    st.logout()
    
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
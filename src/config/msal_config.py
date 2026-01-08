"""
Microsoft Authentication Library (MSAL) configuration for Streamlit.
Integrates with Microsoft Entra ID (formerly Azure AD).
"""

import os
import json
from typing import Optional, Dict
import streamlit as st
import msal
import requests
import secrets


class MSALConfig:
    """MSAL authentication configuration and client management."""
    
    def __init__(self):
        self.client_id = os.environ.get("AZURE_CLIENT_ID", "")
        self.client_secret = os.environ.get("AZURE_CLIENT_SECRET", "")
        self.tenant_id = os.environ.get("AZURE_TENANT_ID", "")
        self.redirect_uri = os.environ.get("AZURE_REDIRECT_URI", "http://localhost:8501/auth-redirect")
        self.authority = f"https://login.microsoftonline.com/{self.tenant_id}"
        self.scope = ["User.Read"]
        self._msal_app = None
    
    @property
    def msal_app(self):
        """Get or create MSAL confidential client application."""
        if self._msal_app is None and self.client_id and self.client_secret:
            self._msal_app = msal.ConfidentialClientApplication(
                self.client_id,
                authority=self.authority,
                client_credential=self.client_secret,
            )
        return self._msal_app
    
    @property
    def is_configured(self) -> bool:
        """Check if MSAL credentials are configured."""
        return bool(self.client_id and self.client_secret and self.tenant_id)
    
    @property
    def is_enabled(self) -> bool:
        """Check if authentication is enabled (configured and not disabled)."""
        auth_disabled = os.environ.get("AUTH_DISABLED", "false").lower() == "true"
        return self.is_configured and not auth_disabled
    
    def show_auth_warning(self):
        """Display warning if authentication is not properly configured."""
        if not self.is_configured:
            st.warning(
                "⚠️ **Microsoft Entra ID authentication not configured!** "
                "To enable authentication, set the following environment variables:\n"
                "- `AZURE_CLIENT_ID` (Application/Client ID)\n"
                "- `AZURE_CLIENT_SECRET` (Client Secret)\n"
                "- `AZURE_TENANT_ID` (Directory/Tenant ID)\n"
                "- `AZURE_REDIRECT_URI` (e.g., https://your-app.azurecontainerapps.io)\n\n"
                "Or set `AUTH_DISABLED=true` to disable authentication."
            )
    
    def initialize_session(self):
        """Initialize authentication session state."""
        if "auth_user" not in st.session_state:
            st.session_state.auth_user = None
        if "auth_token" not in st.session_state:
            st.session_state.auth_token = None
        if "auth_state" not in st.session_state:
            st.session_state.auth_state = None
    
    def is_authenticated(self) -> bool:
        """Check if user is authenticated."""
        if not self.is_enabled:
            return True  # Auth disabled, allow access
        return st.session_state.get("auth_user") is not None
    
    def get_user_info(self) -> Optional[Dict]:
        """Get authenticated user information."""
        return st.session_state.get("auth_user")
    
    def get_authorization_url(self) -> str:
        """Generate Microsoft authorization URL."""
        if not self.msal_app:
            return ""
        
        # Generate random state for CSRF protection
        state = secrets.token_urlsafe(32)
        st.session_state.auth_state = state
        
        auth_url = self.msal_app.get_authorization_request_url(
            scopes=self.scope,
            state=state,
            redirect_uri=self.redirect_uri
        )
        
        return auth_url
    
    def exchange_code_for_token(self, code: str) -> Optional[Dict]:
        """Exchange authorization code for access token."""
        if not self.msal_app:
            return None
        
        try:
            result = self.msal_app.acquire_token_by_authorization_code(
                code=code,
                scopes=self.scope,
                redirect_uri=self.redirect_uri
            )
            
            if "access_token" in result:
                return result
            else:
                error = result.get("error", "Unknown error")
                error_desc = result.get("error_description", "No description")
                st.error(f"Failed to acquire token: {error} - {error_desc}")
                return None
                
        except Exception as e:
            st.error(f"Exception during token exchange: {e}")
            return None
    
    def get_user_info_from_token(self, access_token: str) -> Optional[Dict]:
        """Get user information from Microsoft Graph API using access token."""
        graph_url = "https://graph.microsoft.com/v1.0/me"
        
        headers = {"Authorization": f"Bearer {access_token}"}
        
        try:
            response = requests.get(graph_url, headers=headers)
            response.raise_for_status()
            user_data = response.json()
            
            # Normalize to match Auth0 structure
            return {
                "sub": user_data.get("id"),
                "name": user_data.get("displayName"),
                "email": user_data.get("mail") or user_data.get("userPrincipalName"),
                "preferred_username": user_data.get("userPrincipalName"),
                "given_name": user_data.get("givenName"),
                "family_name": user_data.get("surname"),
            }
        except Exception as e:
            st.error(f"Failed to get user info: {e}")
            return None
    
    def handle_callback(self):
        """Handle OAuth callback from Microsoft."""
        query_params = st.query_params
        
        # Check if we have an authorization code
        if "code" in query_params:
            code = query_params["code"]
            state = query_params.get("state")
            
            # Verify state to prevent CSRF
            if state != st.session_state.get("auth_state"):
                st.error("Invalid state parameter. Possible CSRF attack.")
                return
            
            # Exchange code for token
            token_response = self.exchange_code_for_token(code)
            
            if token_response and "access_token" in token_response:
                access_token = token_response["access_token"]
                
                # Get user info from Microsoft Graph
                user_info = self.get_user_info_from_token(access_token)
                
                if user_info:
                    st.session_state.auth_user = user_info
                    st.session_state.auth_token = access_token
                    
                    # Clear query parameters
                    st.query_params.clear()
                    st.rerun()
        
        # Handle errors
        elif "error" in query_params:
            error = query_params.get("error")
            error_desc = query_params.get("error_description", "No description")
            st.error(f"Authentication error: {error} - {error_desc}")
    
    def render_login_page(self):
        """Render a login page with Microsoft login button."""
        st.markdown(
            """
            <div style="text-align: center; margin: 100px 0;">
                <h1 style="color: #FF6B6B;">Contract Analyzer</h1>
                <p style="font-size: 1.2em; color: #666;">Please log in to continue</p>
            </div>
            """,
            unsafe_allow_html=True
        )
        
        # Create a login button
        col1, col2, col3 = st.columns([1, 1, 1])
        with col2:
            if st.button("🔐 Login with Microsoft", use_container_width=True, type="primary"):
                # Generate authorization URL and redirect
                auth_url = self.get_authorization_url()
                if auth_url:
                    st.markdown(
                        f'<meta http-equiv="refresh" content="0; url={auth_url}">',
                        unsafe_allow_html=True
                    )
                    st.stop()
                else:
                    st.error("Failed to generate authorization URL. Check configuration.")
    
    def render_user_menu(self):
        """Render user menu in the app."""
        if self.is_authenticated():
            user_info = self.get_user_info()
            if user_info:
                st.sidebar.markdown("---")
                st.sidebar.markdown(f"**User:** {user_info.get('name', 'Unknown')}")
                st.sidebar.markdown(f"**Email:** {user_info.get('email', 'N/A')}")
                
                if st.sidebar.button("Logout", key="logout_btn"):
                    st.session_state.auth_user = None
                    st.session_state.auth_token = None
                    st.rerun()
    
    def logout(self):
        """Clear authentication session."""
        st.session_state.auth_user = None
        st.session_state.auth_token = None
        st.session_state.auth_state = None


# Global MSAL configuration instance
msal_config = MSALConfig()

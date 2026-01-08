"""
Configuration settings for the Contract Analyzer application.
Handles Azure OpenAI client initialization and environment variables.
"""

import os
from typing import Optional

import streamlit as st
from dotenv import load_dotenv
from openai import AzureOpenAI
"""Configuration settings for the Contract Analyzer application."""

# Load environment variables from .env if present so Streamlit sessions pick them up
load_dotenv()


class AppConfig:
    """Application configuration for page availability."""
    
    def __init__(self):
        # Get environment mode from environment variable
        # Set APP_ENVIRONMENT to 'mehler' to show only dashboard and use cases
        # Any other value (or unset) will show all pages
        self.environment = os.environ.get("APP_ENVIRONMENT", "full")
    
    @property
    def is_mehler_mode(self) -> bool:
        """Check if app is in 'mehler' mode (only dashboard and use cases)."""
        return self.environment.lower() == "mehler"
    
    def get_available_pages(self) -> list:
        """Get list of available page identifiers based on environment."""
        if self.is_mehler_mode:
            return ["dashboard", "mehler_cases"] 
        else:
            return ["dashboard", "product_detection", "invoice_detection", "detailed_analysis", "mehler_cases"]


class AzureConfig:
    """Azure OpenAI configuration and client management."""
    
    def __init__(self):
        self.api_key = os.environ.get("AZURE_OPENAI_API_KEY")
        self.azure_endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT")
        self.deployment_name = "o4-mini"
        self.api_version = "2024-12-01-preview"
        self._client = None
    
    @property
    def client(self) -> Optional[AzureOpenAI]:
        """Get Azure OpenAI client, initialize if needed."""
        if self._client is None and self.api_key and self.azure_endpoint:
            try:
                self._client = AzureOpenAI(
                    api_key=self.api_key,
                    api_version=self.api_version,
                    azure_endpoint=self.azure_endpoint
                )
            except Exception as e:
                st.error(f"Failed to initialize Azure OpenAI client: {e}")
                return None
        return self._client
    
    @property
    def is_configured(self) -> bool:
        """Check if Azure OpenAI credentials are configured."""
        return bool(self.api_key and self.azure_endpoint)
    
    def show_credentials_warning(self):
        """Display warning if credentials are not configured."""
        if not self.is_configured:
            st.warning(
                "⚠️ **Azure OpenAI credentials not configured!** "
                "To enable AI analysis, set the following environment variables:\n"
                "- `AZURE_OPENAI_API_KEY`\n"
                "- `AZURE_OPENAI_ENDPOINT`\n\n"
                "Currently, only text extraction will work."
            )


# Global configuration instances
app_config = AppConfig()
azure_config = AzureConfig()
"""Framework-independent runtime configuration."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal, Optional

from openai import AzureOpenAI
from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Settings supplied by the Container App or local development environment."""

    model_config = SettingsConfigDict(
        case_sensitive=False,
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    entra_api_audience: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("ENTRA_API_AUDIENCE", "ENTRA_AUDIENCE"),
    )
    entra_allowed_tenant_ids: Optional[str] = Field(default=None, validation_alias="ENTRA_ALLOWED_TENANT_IDS")
    auth_clock_skew_seconds: int = Field(default=60, ge=0, le=300)

    azure_storage_account_url: Optional[str] = Field(default=None, validation_alias="AZURE_STORAGE_ACCOUNT_URL")
    azure_storage_connection_string: Optional[str] = Field(default=None, validation_alias="AZURE_STORAGE_CONNECTION_STRING")
    azure_storage_container_name: Literal["contract-analyzer"] = Field(
        default="contract-analyzer",
        validation_alias="AZURE_STORAGE_CONTAINER_NAME",
    )

    azure_openai_api_key: Optional[str] = Field(default=None, validation_alias="AZURE_OPENAI_API_KEY")
    azure_openai_endpoint: Optional[str] = Field(default=None, validation_alias="AZURE_OPENAI_ENDPOINT")
    azure_openai_deployment: str = Field(default="o4-mini", validation_alias="AZURE_OPENAI_DEPLOYMENT")
    azure_openai_api_version: str = Field(default="2024-12-01-preview", validation_alias="AZURE_OPENAI_API_VERSION")

    azure_mistral_document_ai_endpoint: Optional[str] = Field(
        default=None,
        validation_alias="AZURE_MISTRAL_DOCUMENT_AI_ENDPOINT",
    )
    azure_mistral_document_ai_api_key: Optional[str] = Field(
        default=None,
        validation_alias="AZURE_MISTRAL_DOCUMENT_AI_API_KEY",
    )
    azure_mistral_document_ai_model: str = Field(
        default="mistral-document-ai-2512",
        validation_alias="AZURE_MISTRAL_DOCUMENT_AI_MODEL",
    )
    azure_mistral_document_ai_timeout_seconds: int = Field(
        default=90,
        ge=5,
        le=300,
        validation_alias="AZURE_MISTRAL_DOCUMENT_AI_TIMEOUT_SECONDS",
    )

    searxng_url: Optional[str] = Field(default=None, validation_alias="SEARXNG_URL")
    searxng_timeout_seconds: int = Field(default=20, ge=1, le=120)
    searxng_max_results: int = Field(default=10, ge=1, le=20)

    max_file_bytes: int = Field(default=25 * 1024 * 1024, ge=1024 * 1024)
    max_total_upload_bytes: int = Field(default=100 * 1024 * 1024, ge=1024 * 1024)
    max_files_per_job: int = Field(default=30, ge=1, le=100)
    max_zip_files: int = Field(default=100, ge=1, le=1000)
    max_zip_uncompressed_bytes: int = Field(default=150 * 1024 * 1024, ge=1024 * 1024)
    max_zip_compressed_bytes: int = Field(default=50 * 1024 * 1024, ge=1024 * 1024)
    job_poll_seconds: int = Field(default=10, ge=2, le=60)
    job_recovery_seconds: int = Field(default=300, ge=60, le=3600)
    job_lease_seconds: int = Field(default=60, ge=15, le=60)
    job_concurrency: int = Field(default=1, ge=1, le=4)

    @property
    def storage_configured(self) -> bool:
        return bool(self.azure_storage_connection_string or self.azure_storage_account_url)

    @property
    def auth_configured(self) -> bool:
        return bool(self.entra_api_audience)

    @property
    def mistral_document_ai_configured(self) -> bool:
        return bool(self.azure_mistral_document_ai_endpoint and self.azure_mistral_document_ai_api_key)

    @property
    def allowed_tenant_ids(self) -> frozenset[str]:
        """Return an optional comma-separated allow-list normalized for comparisons."""
        if not self.entra_allowed_tenant_ids:
            return frozenset()
        return frozenset(
            tenant_id.strip().lower()
            for tenant_id in self.entra_allowed_tenant_ids.split(",")
            if tenant_id.strip()
        )


class AzureConfig:
    """Lazily creates the Azure OpenAI client used by existing analysis utilities."""

    def __init__(self) -> None:
        self._client: Optional[AzureOpenAI] = None

    @property
    def deployment_name(self) -> str:
        return get_settings().azure_openai_deployment

    @property
    def is_configured(self) -> bool:
        settings = get_settings()
        return bool(settings.azure_openai_api_key and settings.azure_openai_endpoint)

    @property
    def client(self) -> Optional[AzureOpenAI]:
        if self._client is None and self.is_configured:
            settings = get_settings()
            self._client = AzureOpenAI(
                api_key=settings.azure_openai_api_key,
                api_version=settings.azure_openai_api_version,
                azure_endpoint=settings.azure_openai_endpoint,
            )
        return self._client


@lru_cache
def get_settings() -> Settings:
    return Settings()


azure_config = AzureConfig()

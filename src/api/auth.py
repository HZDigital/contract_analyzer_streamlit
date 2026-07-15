"""Strict Microsoft Entra access-token validation for API requests."""

from __future__ import annotations

import time
from dataclasses import dataclass
from threading import Lock
from typing import Any

import httpx
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import InvalidTokenError

from .schemas import CurrentUser
from .settings import Settings, get_settings


bearer_scheme = HTTPBearer(auto_error=False)
_validator_lock = Lock()
_validator: "EntraTokenValidator | None" = None
_validator_config: tuple[str | None, str | None, int] | None = None


@dataclass
class _JwksCache:
    keys: dict[str, Any]
    issuer: str
    expires_at: float


class EntraTokenValidator:
    """Validates organizational Entra tokens for the configured API audience."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._cache: _JwksCache | None = None
        self._lock = Lock()

    def _load_keys(self) -> _JwksCache:
        if not self.settings.auth_configured:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="API authentication is not configured.")

        now = time.monotonic()
        with self._lock:
            if self._cache and self._cache.expires_at > now:
                return self._cache

            discovery_url = "https://login.microsoftonline.com/organizations/v2.0/.well-known/openid-configuration"
            try:
                with httpx.Client(timeout=10) as client:
                    discovery = client.get(discovery_url)
                    discovery.raise_for_status()
                    metadata = discovery.json()
                    jwks = client.get(metadata["jwks_uri"])
                    jwks.raise_for_status()
                    key_set = jwks.json()["keys"]
            except (httpx.HTTPError, KeyError, ValueError) as exc:
                raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Unable to load Entra signing keys.") from exc

            self._cache = _JwksCache(
                keys={key["kid"]: key for key in key_set if key.get("kid")},
                issuer=metadata["issuer"],
                expires_at=now + 3600,
            )
            return self._cache

    def validate(self, token: str) -> CurrentUser:
        try:
            header = jwt.get_unverified_header(token)
            if header.get("alg") != "RS256" or not header.get("kid"):
                raise InvalidTokenError("Unexpected signing algorithm")
            cache = self._load_keys()
            jwk = cache.keys.get(header["kid"])
            if jwk is None:
                # Key rollover: refresh once rather than trusting a non-cached key.
                self._cache = None
                cache = self._load_keys()
                jwk = cache.keys.get(header["kid"])
            if jwk is None:
                raise InvalidTokenError("Unknown signing key")
            key = jwt.algorithms.RSAAlgorithm.from_jwk(jwk)
            claims = jwt.decode(
                token,
                key=key,
                algorithms=["RS256"],
                audience=self.settings.entra_api_audience,
                leeway=self.settings.auth_clock_skew_seconds,
                options={"require": ["exp", "nbf", "iat", "tid", "iss", "ver"], "verify_iss": False},
            )
        except HTTPException:
            raise
        except (InvalidTokenError, ValueError, TypeError) as exc:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid access token.") from exc

        tenant_id = claims.get("tid")
        if not isinstance(tenant_id, str) or not tenant_id:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token has no tenant identity.")
        allowed_tenants = self.settings.allowed_tenant_ids
        if allowed_tenants and tenant_id.lower() not in allowed_tenants:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token tenant is not allowed.")
        token_version = claims.get("ver")
        expected_issuers = {
            "2.0": f"https://login.microsoftonline.com/{tenant_id}/v2.0",
            "1.0": f"https://sts.windows.net/{tenant_id}/",
        }
        if not isinstance(token_version, str) or claims.get("iss") != expected_issuers.get(token_version):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token issuer is not allowed.")
        oid = claims.get("oid")
        subject = claims.get("sub")
        if not isinstance(oid, str) or not oid or not isinstance(subject, str) or not subject:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token has no user identity.")
        return CurrentUser(
            oid=oid,
            subject=subject,
            tenant_id=tenant_id,
            name=claims.get("name"),
            preferred_username=claims.get("preferred_username"),
        )


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    settings: Settings = Depends(get_settings),
) -> CurrentUser:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Bearer authentication is required.")
    global _validator, _validator_config
    config = (
        settings.entra_api_audience,
        settings.entra_allowed_tenant_ids,
        settings.auth_clock_skew_seconds,
    )
    with _validator_lock:
        if _validator is None or _validator_config != config:
            _validator = EntraTokenValidator(settings)
            _validator_config = config
    return _validator.validate(credentials.credentials)

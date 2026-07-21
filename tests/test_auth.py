import json
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException

from src.api.auth import EntraTokenValidator, _JwksCache
from src.api.settings import Settings


def _validator_and_token(
    *,
    audience: str = "analyzer-client-id",
    tenant_id: str = "tenant-id",
    allowed_tenant_ids: str | None = None,
    issuer: str | None = None,
    token_version: str = "2.0",
) -> tuple[EntraTokenValidator, str]:
    settings = Settings.model_validate(
        {
            "ENTRA_API_AUDIENCE": "analyzer-client-id",
            "ENTRA_ALLOWED_TENANT_IDS": allowed_tenant_ids,
        }
    )
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(private_key.public_key()))
    jwk["kid"] = "test-key"
    validator = EntraTokenValidator(settings)
    validator._load_keys = lambda: _JwksCache(  # type: ignore[method-assign]
        keys={"test-key": jwk},
        issuer="https://login.microsoftonline.com/{tenantid}/v2.0",
        expires_at=float("inf"),
    )
    now = datetime.now(timezone.utc)
    token = jwt.encode(
        {
            "aud": audience,
            "iss": issuer
            or (
                f"https://login.microsoftonline.com/{tenant_id}/v2.0"
                if token_version == "2.0"
                else f"https://sts.windows.net/{tenant_id}/"
            ),
            "tid": tenant_id,
            "ver": token_version,
            "oid": "object-id",
            "sub": "subject-id",
            "iat": now,
            "nbf": now,
            "exp": now + timedelta(minutes=5),
        },
        private_key,
        algorithm="RS256",
        headers={"kid": "test-key"},
    )
    return validator, token


def test_validator_accepts_the_configured_analyzer_audience_without_a_custom_scope() -> None:
    validator, token = _validator_and_token()

    user = validator.validate(token)

    assert user.oid == "object-id"
    assert user.subject == "subject-id"


def test_validator_rejects_a_token_for_another_audience() -> None:
    validator, token = _validator_and_token(audience="https://graph.microsoft.com")

    with pytest.raises(HTTPException) as error:
        validator.validate(token)

    assert error.value.status_code == 401


def test_validator_accepts_tokens_from_multiple_tenants() -> None:
    first_validator, first_token = _validator_and_token(tenant_id="tenant-one")
    second_validator, second_token = _validator_and_token(tenant_id="tenant-two")

    assert first_validator.validate(first_token).tenant_id == "tenant-one"
    assert second_validator.validate(second_token).tenant_id == "tenant-two"


def test_validator_accepts_a_v1_token_for_the_signed_tenant() -> None:
    validator, token = _validator_and_token(token_version="1.0")

    assert validator.validate(token).tenant_id == "tenant-id"


def test_validator_enforces_an_optional_tenant_allow_list() -> None:
    validator, token = _validator_and_token(tenant_id="tenant-two", allowed_tenant_ids="tenant-one")

    with pytest.raises(HTTPException) as error:
        validator.validate(token)

    assert error.value.status_code == 401


def test_validator_rejects_an_issuer_that_does_not_match_the_signed_tenant() -> None:
    validator, token = _validator_and_token(
        issuer="https://login.microsoftonline.com/another-tenant/v2.0",
    )

    with pytest.raises(HTTPException) as error:
        validator.validate(token)

    assert error.value.status_code == 401

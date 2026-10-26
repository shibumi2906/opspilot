import json
import time

import jwt
import pytest

from opspilot.auth.context import AuthError
from opspilot.auth.service_context import mint, verify
from opspilot.cli.service_keys import initialize, main
from opspilot.config import Settings
from opspilot.tenancy.context import DEMO_TENANT, tenant_scope


def key_settings(path):
    initialize(path)
    return Settings(
        mcp_service_token="a" * 64,
        app_env="test",
        service_private_dir=str(path / "private"),
        service_public_keys=str(path / "public" / "keys.json"),
    )


@pytest.mark.parametrize(
    "failure",
    ["issuer", "audience", "expired", "signature", "algorithm", "kid", "tenant", "lifetime"],
)
def test_service_context_rejects_wrong_authority(tmp_path, failure):
    settings = key_settings(tmp_path)
    with tenant_scope(DEMO_TENANT):
        token = mint(settings)
    claims = jwt.decode(token, options={"verify_signature": False})
    headers = {"kid": "current"}
    key = (tmp_path / "private" / "current.pem").read_text()
    if failure == "issuer":
        claims["iss"] = "https://oidc.invalid"
    if failure == "audience":
        claims["aud"] = "other-service"
    if failure == "expired":
        claims.update(
            iat=int(time.time()) - 90, nbf=int(time.time()) - 90, exp=int(time.time()) - 30
        )
    if failure == "signature":
        key = (tmp_path / "private" / "next.pem").read_text()
    if failure == "kid":
        headers["kid"] = "unknown"
    if failure == "tenant":
        claims["tenant"] = "forged"
    if failure == "lifetime":
        claims["exp"] = claims["iat"] + 3600
    token = jwt.encode(claims, key, algorithm="EdDSA", headers=headers)
    if failure == "algorithm":
        token = jwt.encode(claims, "b" * 64, algorithm="HS256", headers=headers)
    with pytest.raises(AuthError):
        verify(token, settings)


def test_service_key_rotation_and_environment_audience(tmp_path, monkeypatch):
    settings = key_settings(tmp_path)
    with tenant_scope(DEMO_TENANT):
        old = mint(settings)
        new = mint(settings.model_copy(update={"service_active_kid": "next"}))
    assert verify(old, settings)["tenant"] == str(DEMO_TENANT)
    assert verify(new, settings)["tenant"] == str(DEMO_TENANT)
    with pytest.raises(AuthError):
        verify(old, settings.model_copy(update={"app_env": "local"}))
    monkeypatch.setattr(
        "sys.argv", ["service_keys", str(tmp_path), "--retire", "current", "--active", "next"]
    )
    main()
    with pytest.raises(AuthError):
        verify(old, settings)
    assert verify(new, settings)["scope"] == "read"
    assert "PRIVATE KEY" not in (tmp_path / "public" / "keys.json").read_text()
    assert set(json.loads((tmp_path / "public" / "keys.json").read_text())) == {"next"}

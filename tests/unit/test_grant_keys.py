import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import jwt
import pytest
from pydantic import ValidationError

from opspilot.auth.context import AuthError
from opspilot.cli.service_keys import initialize
from opspilot.config import Settings
from opspilot.contracts.api import Decision
from opspilot.security.grants import verify
from opspilot.security.keys import FileGrantKeys


def token_fixture(tmp_path):
    initialize(tmp_path)
    settings = Settings(
        _env_file=None,
        mcp_service_token="a" * 64,
        service_private_dir=str(tmp_path / "private"),
        service_public_keys=str(tmp_path / "public/keys.json"),
    )
    provider = FileGrantKeys(settings.service_private_dir, settings.service_public_keys)
    now = datetime.now(UTC)
    claims = {
        "iss": "urn:opspilot:grant:" + settings.app_env,
        "aud": "urn:opspilot:execute:" + settings.app_env,
        "ver": 1,
        "tool": "create_ticket",
        "iat": int(now.timestamp()),
        "nbf": int(now.timestamp()),
        "exp": int(now.timestamp()) + 55,
        "jti": str(uuid4()),
        "tenant": str(uuid4()),
        "run": str(uuid4()),
        "revision": str(uuid4()),
        "actor": str(uuid4()),
        "approver": str(uuid4()),
        "payload_hash": "a" * 64,
        "epoch": 1,
    }
    return settings, provider, claims, now


def test_independent_grant_key_versions_and_retirement(tmp_path):
    settings, provider, claims, now = token_fixture(tmp_path)
    issued = []
    for slot in ["grant-current", "grant-next"]:
        ref, key = provider.signing_key(slot)
        assert ref.purpose == "execution-grant-v1" and len(ref.kid.split(":")[1]) == 64
        token = jwt.encode(
            claims,
            key,
            algorithm="EdDSA",
            headers={"kid": ref.kid, "typ": "opspilot-execution+jwt"},
        )
        assert verify(token, settings, now=now)["jti"] == claims["jti"]
        issued.append(token)
    ring = Path(settings.service_public_keys).with_name("grants.json")
    value = json.loads(ring.read_text())
    value.pop("grant-current")
    ring.write_text(json.dumps(value))
    with pytest.raises(AuthError):
        verify(issued[0], settings, now=now)
    assert verify(issued[1], settings, now=now)["jti"] == claims["jti"]
    with pytest.raises(ValueError):
        provider.signing_key("../current")


@pytest.mark.parametrize(
    "change",
    [
        "expired",
        "future",
        "boolean_epoch",
        "boolean_version",
        "long_ttl",
        "wrong_purpose",
        "service_key",
        "hs256",
    ],
)
def test_grant_verifier_uses_authoritative_clock_and_purpose(tmp_path, change):
    settings, provider, claims, now = token_fixture(tmp_path)
    ref, key = provider.signing_key("grant-current")
    if change == "expired":
        claims["exp"] = claims["iat"] - 1
    if change == "future":
        claims["iat"] += 100
        claims["nbf"] += 100
        claims["exp"] += 100
    if change == "boolean_epoch":
        claims["epoch"] = True
    if change == "boolean_version":
        claims["ver"] = True
    if change == "long_ttl":
        claims["exp"] = claims["iat"] + 61
    kind = "JWT" if change == "wrong_purpose" else "opspilot-execution+jwt"
    kid = ref.kid
    if change == "service_key":
        kid = "current"
        key = (tmp_path / "private/current.pem").read_bytes()
    algorithm = "HS256" if change == "hs256" else "EdDSA"
    if change == "hs256":
        key = b"x" * 64
    token = jwt.encode(claims, key, algorithm=algorithm, headers={"kid": kid, "typ": kind})
    with pytest.raises(AuthError):
        verify(token, settings, now=now)


def test_grant_verification_does_not_depend_on_worker_wall_clock(tmp_path):
    settings, provider, claims, now = token_fixture(tmp_path)
    ref, key = provider.signing_key("grant-current")
    token = jwt.encode(
        claims, key, algorithm="EdDSA", headers={"kid": ref.kid, "typ": "opspilot-execution+jwt"}
    )
    assert verify(token, settings, now=now)["exp"] == claims["exp"]
    with pytest.raises(AuthError):
        verify(token, settings, now=now + timedelta(seconds=60))


@pytest.mark.parametrize("version", [None, True, 1.0, "1", 0, -1, 11])
def test_decision_version_is_required_strict_and_bounded(version):
    with pytest.raises(ValidationError):
        Decision(action_id=uuid4(), decision="approve", expected_version=version)

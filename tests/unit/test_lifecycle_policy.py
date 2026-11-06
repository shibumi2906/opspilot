import pytest
from pydantic import ValidationError

from opspilot.security.lifecycle import RetentionPolicy
from opspilot.security.manager import BaoGrantKeys


@pytest.mark.parametrize(
    "value",
    [
        {"evidence_days": 0},
        {"history_days": 29},
        {"audit_days": 89},
        {"evidence_days": 3651},
        {"delete_active": True},
        {"batch_size": 0},
        {"batch_size": 101},
        {"evidence_days": True},
    ],
)
def test_retention_rejects_unsafe_configuration(value):
    with pytest.raises(ValidationError):
        RetentionPolicy(**value)


def test_retention_policy_change_can_be_reversed_exactly():
    original = RetentionPolicy()
    changed = RetentionPolicy(evidence_days=60)
    assert changed.digest() != original.digest()
    assert (
        RetentionPolicy.model_validate_json(original.model_dump_json()).digest()
        == original.digest()
    )


@pytest.mark.parametrize(
    "origin",
    [
        "http://manager:8200",
        "https://user:password@manager",
        "https://manager/path",
        "https://manager?token=x",
        "https://manager#token",
        "file:///run/secrets",
    ],
)
def test_manager_rejects_untrusted_origin_configuration(origin):
    with pytest.raises(ValueError):
        BaoGrantKeys(origin, "/missing-ca", "/missing-token")


@pytest.mark.parametrize(
    "path", ["../root", "grants/private/0", "tenants/a/key", "grants/private/1?version=2"]
)
def test_manager_rejects_unregistered_reference_before_io(path):
    with pytest.raises(ValueError, match="Unregistered"):
        BaoGrantKeys("https://manager:8200", "/missing-ca", "/missing-token").read(path)


def test_grant_verifier_sanitizes_manager_failure(monkeypatch):
    from datetime import UTC, datetime
    from types import SimpleNamespace

    import jwt
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    from opspilot.auth.context import AuthError
    from opspilot.security import grants
    from opspilot.security.manager import ManagerUnavailable

    class Denied:
        def verification_key(self, kid):
            raise ManagerUnavailable()

    monkeypatch.setattr(grants, "grant_keys", lambda _: Denied())
    token = jwt.encode(
        {},
        Ed25519PrivateKey.generate(),
        algorithm="EdDSA",
        headers={"typ": "opspilot-execution+jwt", "kid": "grant-current:" + "a" * 64},
    )
    with pytest.raises(AuthError) as failure:
        grants.verify(token, SimpleNamespace(app_env="test"), now=datetime.now(UTC))
    assert failure.value.code == "GRANT_INVALID"

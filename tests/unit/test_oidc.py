import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from opspilot.auth.context import AuthError
from opspilot.auth.oidc import digest, verify_id_token
from opspilot.config import Settings


@pytest.mark.parametrize(
    "change", ["issuer", "audience", "signature", "nonce", "expiry", "algorithm"]
)
def test_oidc_rejects_invalid_trust_claims(change):
    settings = Settings(mcp_service_token="a" * 64)
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jwk = jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key(), as_dict=True)
    jwk["kid"] = "test"
    claims = {
        "iss": settings.oidc_issuer,
        "aud": settings.oidc_client_id,
        "sub": "synthetic",
        "iat": int(time.time()),
        "exp": int(time.time()) + 300,
        "nonce": "nonce",
    }
    if change == "issuer":
        claims["iss"] = "https://evil.invalid"
    if change == "audience":
        claims["aud"] = "other-client"
    if change == "expiry":
        claims["exp"] = int(time.time()) - 1
    if change == "nonce":
        claims["nonce"] = "other"
    signer = (
        rsa.generate_private_key(public_exponent=65537, key_size=2048)
        if change == "signature"
        else key
    )
    token = jwt.encode(claims, signer, algorithm="RS256", headers={"kid": "test"})
    if change == "algorithm":
        token = jwt.encode(claims, "a" * 64, algorithm="HS256", headers={"kid": "test"})
    with pytest.raises(AuthError):
        verify_id_token(token, {"keys": [jwk]}, settings, digest("nonce"))

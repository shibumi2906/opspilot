"""Bounded OIDC authorization code/PKCE client with pinned issuer and RS256 JWKS."""

import hashlib
import secrets
from base64 import urlsafe_b64encode
from typing import Any
from urllib.parse import urlencode

import httpx
import jwt

from opspilot.auth.context import AuthError
from opspilot.config import Settings


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def challenge(verifier: str) -> str:
    return urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()


def verify_id_token(
    token: str, jwks: dict[str, Any], settings: Settings, nonce_hash: str
) -> dict[str, Any]:
    try:
        header = jwt.get_unverified_header(token)
        if header.get("alg") != "RS256" or not isinstance(header.get("kid"), str):
            raise AuthError("OIDC_INVALID", 400)
        matches = [
            k
            for k in jwks.get("keys", [])
            if k.get("kid") == header["kid"]
            and k.get("kty") == "RSA"
            and k.get("use", "sig") == "sig"
            and k.get("alg", "RS256") == "RS256"
        ]
        if len(matches) != 1:
            raise AuthError("OIDC_INVALID", 400)
        key = jwt.PyJWK.from_dict(matches[0], algorithm="RS256").key
        claims: dict[str, Any] = jwt.decode(
            token,
            key,
            algorithms=["RS256"],
            issuer=settings.oidc_issuer,
            audience=settings.oidc_client_id,
            options={"require": ["iss", "aud", "exp", "iat", "sub", "nonce"]},
        )
        if not secrets.compare_digest(digest(str(claims["nonce"])), nonce_hash):
            raise AuthError("OIDC_INVALID", 400)
        if not isinstance(claims["sub"], str) or not claims["sub"]:
            raise AuthError("OIDC_INVALID", 400)
        if (
            isinstance(claims["aud"], list)
            and len(claims["aud"]) > 1
            and claims.get("azp") != settings.oidc_client_id
        ):
            raise AuthError("OIDC_INVALID", 400)
        return claims
    except (jwt.PyJWTError, ValueError, KeyError, TypeError) as exc:
        raise AuthError("OIDC_INVALID", 400) from exc


class OIDC:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @property
    def callback(self) -> str:
        return self.settings.app_origin + "/auth/callback"

    def authorization(self, state: str, nonce: str, verifier: str) -> str:
        return (
            self.settings.oidc_issuer
            + "/protocol/openid-connect/auth?"
            + urlencode(
                {
                    "client_id": self.settings.oidc_client_id,
                    "response_type": "code",
                    "scope": "openid profile",
                    "redirect_uri": self.callback,
                    "state": state,
                    "nonce": nonce,
                    "code_challenge": challenge(verifier),
                    "code_challenge_method": "S256",
                }
            )
        )

    async def exchange(self, code: str, verifier: str, nonce_hash: str) -> dict[str, Any]:
        base = self.settings.oidc_internal_issuer
        async with httpx.AsyncClient(timeout=5, trust_env=False, follow_redirects=False) as client:
            discovery = await client.get(base + "/.well-known/openid-configuration")
            discovery.raise_for_status()
            metadata = discovery.json()
            if metadata.get("issuer") != self.settings.oidc_issuer:
                raise AuthError("OIDC_INVALID", 400)
            for name, path in [("token_endpoint", "token"), ("jwks_uri", "certs")]:
                if (
                    metadata.get(name)
                    != self.settings.oidc_issuer + "/protocol/openid-connect/" + path
                ):
                    raise AuthError("OIDC_INVALID", 400)
            response = await client.post(
                base + "/protocol/openid-connect/token",
                data={
                    "grant_type": "authorization_code",
                    "client_id": self.settings.oidc_client_id,
                    "code": code,
                    "code_verifier": verifier,
                    "redirect_uri": self.callback,
                },
            )
            response.raise_for_status()
            keys = await client.get(base + "/protocol/openid-connect/certs")
            keys.raise_for_status()
            return verify_id_token(
                response.json()["id_token"], keys.json(), self.settings, nonce_hash
            )

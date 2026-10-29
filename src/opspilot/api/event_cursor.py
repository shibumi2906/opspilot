"""Integrity protected cursors are scope references, never authentication credentials."""

import base64
import hashlib
import hmac
import json
from uuid import UUID

from fastapi import Request

from opspilot.auth.context import AuthError, principal


def encode(request: Request, run_id: UUID, sequence: int) -> str:
    user = principal()
    body = [1, str(user.session_id), str(user.user_id), str(user.tenant_id), str(run_id), sequence]
    raw = base64.urlsafe_b64encode(json.dumps(body, separators=(",", ":")).encode()).decode()
    key = request.app.state.identity.settings.session_signing_key.get_secret_value().encode()
    return raw + "." + hmac.new(key, raw.encode(), hashlib.sha256).hexdigest()


def decode(request: Request, run_id: UUID, value: str) -> int:
    try:
        if len(value) > 1024:
            raise ValueError()
        raw, mac = value.split(".")
        key = request.app.state.identity.settings.session_signing_key.get_secret_value().encode()
        if not hmac.compare_digest(mac, hmac.new(key, raw.encode(), hashlib.sha256).hexdigest()):
            raise ValueError()
        body = json.loads(base64.b64decode(raw, altchars=b"-_", validate=True))
        sequence = body[-1]
        if type(sequence) is not int or not 0 <= sequence <= 9223372036854775807:
            raise ValueError()
        if not hmac.compare_digest(encode(request, run_id, sequence), value):
            raise ValueError()
        return sequence
    except (ValueError, TypeError, IndexError, KeyError) as exc:
        raise AuthError("INVALID_CURSOR", 400) from exc

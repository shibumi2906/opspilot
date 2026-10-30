"""Apply only the reviewed policy keys to the existing local Full realm, never users/clients."""

import json
import urllib.request
from pathlib import Path
from urllib.parse import urlencode

values = dict(
    line.split("=", 1)
    for line in Path(".env").read_text(encoding="utf-8-sig").splitlines()
    if "=" in line and not line.startswith("#")
)
issuer = values.get("OIDC_ISSUER", "http://127.0.0.1:8181/realms/opspilot").strip('"')
assert issuer in {"http://127.0.0.1:8181/realms/opspilot", "http://localhost:8181/realms/opspilot"}
base = issuer.split("/realms/")[0]
body = urlencode(
    {
        "client_id": "admin-cli",
        "grant_type": "password",
        "username": "opspilot-local-admin",
        "password": values["OIDC_BOOTSTRAP_PASSWORD"].strip('"'),
    }
).encode()
with urllib.request.urlopen(
    urllib.request.Request(base + "/realms/master/protocol/openid-connect/token", data=body),
    timeout=10,
) as r:
    token = json.load(r)["access_token"]
source = json.loads(Path("infra/identity/opspilot-realm.json").read_text(encoding="utf-8"))
keys = [
    "passwordPolicy",
    "bruteForceProtected",
    "failureFactor",
    "waitIncrementSeconds",
    "maxFailureWaitSeconds",
    "minimumQuickLoginWaitSeconds",
    "eventsEnabled",
    "adminEventsEnabled",
    "adminEventsDetailsEnabled",
    "eventsExpiration",
    "registrationAllowed",
    "resetPasswordAllowed",
]
policy = {k: source[k] for k in keys}
request = urllib.request.Request(
    base + "/admin/realms/opspilot",
    data=json.dumps(policy).encode(),
    headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"},
    method="PUT",
)
with urllib.request.urlopen(request, timeout=10) as r:
    assert r.status == 204
with urllib.request.urlopen(
    urllib.request.Request(
        base + "/admin/realms/opspilot", headers={"Authorization": "Bearer " + token}
    ),
    timeout=10,
) as r:
    actual = json.load(r)
assert all(actual[k] == v for k, v in policy.items())
Path("docs/full/evidence/f14/local-idp-policy.json").write_text(
    json.dumps(
        {
            "passed": True,
            "keys_applied": keys,
            "policy_update_scope": (
                "realm policy keys only; no user/client/credential mutation calls"
            ),
            "password_policy": policy["passwordPolicy"],
            "recovery": (
                "self-service reset disabled; pinned IdP account console and administrator recovery"
            ),
            "full_l2_status": "NOT_MET",
        },
        indent=2,
    )
    + "\n",
    encoding="utf-8",
)
print("Reviewed local Full IdP policy applied; no credentials exported")

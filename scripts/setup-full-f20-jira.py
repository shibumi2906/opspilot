"""Enroll the owner's verified KAN sandbox in an isolated F20 manager/database."""

import argparse
import base64
import json
import re
import socket
import ssl
import subprocess
from pathlib import Path
from uuid import UUID

import httpx

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--project", required=True)
args = parser.parse_args()
if not re.fullmatch(r"opspilot-full-test-f20-[a-z0-9]+", args.project):
    raise SystemExit("Isolated F20 project required")
private = Path(".tools/f20") / args.project
credential = json.loads(Path(".tools/f20-private/credential.json").read_bytes())
site = json.loads(Path(".tools/f20-private/site.json").read_bytes())
assert site["site"] == "https://makegrigorev.atlassian.net"
assert site["project_key"] == "KAN"
tenant, customer, connector = (
    UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"),
    UUID(int=1),
    UUID(int=2020),
)
issue_type = next(
    t
    for t in site["issue_types"]
    if t.get("hierarchyLevel", 0) >= 0 and not t.get("subtask") and t["id"] == "10006"
)["id"]
api_base = credential["api_base"]
cloud = api_base.split("/ex/jira/")[1].split("/")[0] if "/ex/jira/" in api_base else None
host = "api.atlassian.com" if cloud else site["site"].removeprefix("https://")
addresses = sorted({str(r[4][0]) for r in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)})
authorization = (
    "Basic " + base64.b64encode((credential["email"] + ":" + credential["token"]).encode()).decode()
)
with httpx.Client(
    timeout=20, trust_env=False, follow_redirects=False, headers={"Authorization": authorization}
) as client:
    fields = client.get(api_base + f"/issue/createmeta/KAN/issuetypes/{issue_type}")
    fields.raise_for_status()
    entries = fields.json().get("fields", fields.json().get("values", []))
    required = {
        entry.get("fieldId", entry.get("key"))
        for entry in entries
        if entry.get("required") and not entry.get("hasDefaultValue")
    }
    assert required <= {"summary", "project", "issuetype"}, "Unsupported required create field"
context = ssl.create_default_context(cafile=str(private / "manager/ca.crt"))
root = json.loads((private / "recovery/initialization.json").read_bytes())["root_token"]
with httpx.Client(
    base_url="https://127.0.0.1:18240",
    verify=context,
    timeout=10,
    trust_env=False,
    headers={"X-Vault-Token": root},
) as client:
    secret_path = f"connectors/{tenant}/{connector}/credential"
    response = client.post(
        "/v1/core/data/" + secret_path,
        json={
            "data": {
                "tenant_id": str(tenant),
                "connector_id": str(connector),
                "site": site["site"],
                "project_id": site["project_id"],
                "email": credential["email"],
                "token": credential["token"],
            }
        },
    )
    response.raise_for_status()
    policy = (
        'path "core/data/grants/public" { capabilities=["read"] }\n'
        f'path "core/data/{secret_path}" {{ capabilities=["read"] }}'
    )
    response = client.put("/v1/sys/policies/acl/f17-mcp", json={"policy": policy})
    response.raise_for_status()
record = {
    "tenant": str(tenant),
    "connector": str(connector),
    "customer": str(customer),
    "site": site["site"],
    "project": site["project_id"],
    "type": issue_type,
    "addresses": addresses,
    "cloud": cloud,
}
# Literal values are validated above or derived from fixed verified enrollment.
sql = (
    "INSERT INTO integrations.jira_bindings "
    "(tenant_id,connector_id,customer_id,version,site,project_id,issue_type_id,"
    "addresses,cloud_id,enabled) "
    f"VALUES('{tenant}','{connector}','{customer}',1,'{site['site']}',"
    f"'{int(site['project_id'])}','{int(issue_type)}','{json.dumps(addresses)}'::jsonb,"
    + (f"'{UUID(cloud)}'" if cloud else "NULL")
    + ",true);"
)
result = subprocess.run(
    [
        "docker",
        "exec",
        "-i",
        args.project + "-postgres-1",
        "psql",
        "-XAt",
        "-v",
        "ON_ERROR_STOP=1",
        "-U",
        "ops_migration",
        "-d",
        "opspilot_full_test",
    ],
    input=sql,
    capture_output=True,
    text=True,
)
if result.returncode:
    raise SystemExit("F20 trusted enrollment failed; no raw provider or SQL error exported")
(private / "enrollment.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
print("Verified KAN mapping and exact isolated manager ACL enrolled; no Jira writes sent")

"""Private native TLS lab overlay: dedicated ingress DSN and purpose-limited manager token."""

import json
from pathlib import Path

root = Path.cwd()
lab = root / ".tools/security-f18-final"
base = json.loads((lab / "compose.json").read_text())
fixture = json.loads((root / ".tools/f18-private/fixture.json").read_text())
(lab / "ingress.dsn").write_text(
    "postgresql+psycopg://ops_ingress:"
    + fixture["db_password"]
    + "@postgres/opspilot_full_test?sslmode=verify-full&sslrootcert=/tls/ca.crt"
)
services = {}
for name in ("api", "admin", "probe"):
    files = json.loads(base["services"][name]["environment"]["SECRET_FILES"])
    files["ingress_database_url"] = "/secrets/ingress.dsn"
    services[name] = {
        "environment": {"SECRET_FILES": json.dumps(files)},
        "volumes": [str(lab / "ingress.dsn") + ":/secrets/ingress.dsn:ro"],
    }
services["api"]["environment"].update(
    {
        "CONNECTOR_MANAGER_URL": "https://manager:8200",
        "CONNECTOR_MANAGER_CA_FILE": "/run/connectors/manager-ca.crt",
        "CONNECTOR_MANAGER_TOKEN_FILE": "/run/connectors/ingress.token",
    }
)
services["api"]["volumes"] += [
    str(root / ".tools/f18-client/manager-ca.crt") + ":/run/connectors/manager-ca.crt:ro",
    str(root / ".tools/f18-client/ingress.token") + ":/run/connectors/ingress.token:ro",
]
services["probe"]["volumes"] += [
    str(root / ".tools/f18-probe/fixture.json") + ":/run/f18-probe/fixture.json:ro"
]
(lab / "compose-ingress.json").write_text(json.dumps({"services": services}))
print("F18 native verify-full ingress role/manager overlay prepared; values withheld")

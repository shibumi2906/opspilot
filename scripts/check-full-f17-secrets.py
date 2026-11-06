"""Compare changed artifacts with actual local credentials without disclosing them."""

import json
import re
import subprocess
from pathlib import Path
from urllib.parse import urlsplit

values: set[str] = set()


def secret(value: object) -> None:
    if isinstance(value, str) and len(value) >= 8:
        if "://" in value:
            try:
                password = urlsplit(value).password
                if password and len(password) >= 8:
                    values.add(password)
                else:
                    return
            except ValueError:
                pass
        values.add(value.strip())


def collect(value: object) -> None:
    if isinstance(value, dict):
        if value.get("type") in {"password", "totp"}:
            secret(value.get("value"))
            data = value.get("secretData")
            if isinstance(data, str):
                try:
                    for item in json.loads(data).values():
                        secret(item)
                except ValueError:
                    pass
        for key, item in value.items():
            # File references are public configuration. Their actual local contents
            # are collected separately below; do not mistake a path for a token.
            if key.endswith(("_FILE", "_FILES", "_DIR", "_PATH")):
                continue
            if key in {"passwordPolicy", "SECRET_FILES", "SECRET_MANAGER_URL", "SECRET_MANAGER_CA_FILE", "SECRET_MANAGER_TOKEN_FILE"}:
                continue
            if key == "keys" or re.search(r"PASSWORD|TOKEN|SECRET|SIGNING_KEY|TOKEN_KEY|API_KEY|keys_base64|root_token", key, re.I):
                if isinstance(item, list):
                    for member in item:
                        secret(member)
                else:
                    secret(item)
            collect(item)
    elif isinstance(value, list):
        for item in value:
            collect(item)


for line in Path(".env").read_text(encoding="utf-8-sig").splitlines():
    key, separator, value = line.partition("=")
    if separator and re.search(r"PASSWORD|TOKEN|SECRET|SIGNING_KEY|API_KEY|DATABASE_URL", key):
        secret(value.strip().strip("\"'"))
for folder in ("f17-manager", "f17-recovery", "f17-manager-dev", "f17-recovery-dev", "f17-full-recovery", "security-f17-final", "security-f17-final2", "service-keys",
               "observability", "observability-test", "cache", "cache-test"):
    for path in (Path(".tools") / folder).rglob("*"):
        if not path.is_file() or path.stat().st_size > 2_000_000:
            continue
        if path.suffix == ".json":
            try:
                collect(json.loads(path.read_text(encoding="utf-8-sig")))
            except (ValueError, OSError):
                pass
        if re.search(r"token|password|signing|integrity|backup.key|\.dsn$", path.name):
            secret(path.read_text(encoding="utf-8-sig", errors="replace").strip())

files = set(subprocess.check_output(["git", "diff", "--name-only", "6330f32"], text=True).splitlines())
files.update(subprocess.check_output(["git", "ls-files", "--others", "--exclude-standard"], text=True).splitlines())
hits = []
for name in files:
    path = Path(name)
    if path.is_file():
        content = path.read_text(encoding="utf-8-sig", errors="replace")
        if any(value in content for value in values) or re.search(
            r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----", content
        ):
            hits.append(name)
if hits:
    raise RuntimeError("Credential match in artifact paths (values withheld): " + ", ".join(hits))
report = {"changed_artifacts_checked": len(files), "credential_matches": 0,
          "private_key_matches": 0, "secrets_in_report": False,
          "scope": "actual Full env and F17 manager/recovery/TLS/service/cache/telemetry credentials"}
Path("docs/full/evidence/f17/artifact-secret-check.json").write_text(json.dumps(report, indent=2) + "\n")
print(json.dumps(report))

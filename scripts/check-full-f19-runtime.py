"""Actual credential log and operator-material mount checks; export no secret values."""

import json
import re
import runpy
import subprocess
from pathlib import Path

state = runpy.run_path("scripts/check-full-f19-secrets.py")
values = state["values"]
projects = [
    "opspilot-full-test-f19-local-final",
    "opspilot-full-test-f19-regression-r1",
    "opspilot-full",
]
containers = set()
for project in projects:
    containers.update(
        subprocess.check_output(
            ["docker", "ps", "-aq", "--filter", "label=com.docker.compose.project=" + project],
            text=True,
        ).split()
    )
containers.add("opspilot-full-test-f17-manager-r2-manager-1")
mount_checks = 0
for container in sorted(containers):
    logs = subprocess.run(
        ["docker", "logs", "--tail", "20000", container],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        check=True,
    )
    content = logs.stdout + logs.stderr
    assert not any(value in content for value in values), "Credential match (values withheld)"
    assert not re.search(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----", content)
    service = subprocess.check_output(
        [
            "docker",
            "inspect",
            container,
            "--format",
            '{{index .Config.Labels "com.docker.compose.service"}}',
        ],
        text=True,
    ).strip()
    if service in {"api", "mcp", "worker", "worker2", "web"}:
        mounts = json.loads(
            subprocess.check_output(
                ["docker", "inspect", container, "--format", "{{json .Mounts}}"], text=True
            )
        )
        for mount in mounts:
            source = mount["Source"].replace("\\", "/")
            assert not any(x in source for x in ("f19-private", "f17-recovery", "f19-server"))
        mount_checks += 1
result = {
    "passed": True,
    "containers_checked": len(containers),
    "application_mount_checks": mount_checks,
    "credential_matches": 0,
    "private_key_matches": 0,
    "values_exported": False,
    "log_tail_bound_per_container": 20000,
}
Path("docs/full/evidence/f19/runtime-secret-check.json").write_text(
    json.dumps(result, indent=2) + "\n"
)
print(json.dumps(result))

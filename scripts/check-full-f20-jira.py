"""Read-only sandbox preflight. Credentials and provider bodies never reach stdout."""

import base64
import json
import re
from datetime import UTC, datetime
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
PRIVATE = ROOT / ".tools/f20-private"
REPORT = ROOT / "docs/full/evidence/f20/jira-preflight.json"
SITE = "https://makegrigorev.atlassian.net"


def main() -> int:
    report: dict[str, object] = {
        "checked_at": datetime.now(UTC).isoformat(),
        "site": SITE,
        "project_key": "KAN",
        "write_requests": 0,
        "paid_calls": 0,
        "passed": False,
    }
    try:
        credential = json.loads((PRIVATE / "credential.json").read_text())
        with httpx.Client(timeout=20, trust_env=False, follow_redirects=False) as client:
            discovery = client.get(SITE + "/_edge/tenant_info")
            report["discovery_status"] = discovery.status_code
            discovery.raise_for_status()
            cloud = discovery.json()["cloudId"]
            if not re.fullmatch(r"[0-9a-f-]{36}", cloud):
                raise ValueError("invalid cloud identity")
            base = "https://api.atlassian.com/ex/jira/" + cloud + "/rest/api/3"
            auth = base64.b64encode(
                (credential["email"] + ":" + credential["token"]).encode()
            ).decode()
            headers = {"Authorization": "Basic " + auth, "Accept": "application/json"}
            permissions = client.get(
                base + "/mypermissions",
                params={
                    "projectKey": "KAN",
                    "permissions": "BROWSE_PROJECTS,CREATE_ISSUES,ADD_COMMENTS",
                },
                headers=headers,
            )
            report["permission_status"] = permissions.status_code
            permissions.raise_for_status()
            rights = permissions.json()["permissions"]
            allowed = {
                k: rights.get(k, {}).get("havePermission") is True
                for k in ("BROWSE_PROJECTS", "CREATE_ISSUES", "ADD_COMMENTS")
            }
            report["credential_authenticated"] = True
            report["permissions"] = allowed
            project = client.get(base + "/project/KAN", headers=headers)
            report["project_status"] = project.status_code
            report["scope_mismatch"] = (
                project.status_code == 401 and "scope does not match" in project.text.lower()
            )
            project.raise_for_status()
            data = project.json()
            expected = data.get("key") == "KAN" and data.get("name") == "OpsPilot Test"
            report["exact_project_match"] = expected
            if not expected or not re.fullmatch(r"[1-9][0-9]*", data["id"]):
                raise ValueError("project mismatch")
            types = client.get(base + "/issue/createmeta/KAN/issuetypes", headers=headers)
            report["create_metadata_status"] = types.status_code
            types.raise_for_status()
            issue_types = types.json().get("issueTypes", [])
            report["available_issue_type_count"] = len(issue_types)
            (PRIVATE / "site.json").write_text(
                json.dumps(
                    {
                        "site": SITE,
                        "cloud_id": cloud,
                        "project_key": "KAN",
                        "project_id": data["id"],
                        "issue_types": [
                            {"id": t["id"], "name": t["name"], "subtask": t.get("subtask")}
                            for t in issue_types
                        ],
                    }
                ),
                encoding="utf-8",
            )
            report["passed"] = expected and all(allowed.values()) and bool(issue_types)
    except Exception as exc:
        # Provider errors, headers, URLs and response bodies may contain secrets/user data.
        report["error_class"] = type(exc).__name__
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

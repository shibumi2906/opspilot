"""Read-only preflight must distinguish valid-but-under-scoped credentials safely."""

import importlib.util
import json
from pathlib import Path

import httpx
import pytest


@pytest.mark.parametrize("project_status,expected", [(200, True), (401, False), (403, False)])
def test_preflight_never_writes_or_outputs_credentials(
    tmp_path, monkeypatch, capsys, project_status, expected
):
    path = Path(__file__).resolve().parents[2] / "scripts/check-full-f20-jira.py"
    spec = importlib.util.spec_from_file_location("jira_preflight", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.PRIVATE = tmp_path
    module.REPORT = tmp_path / "report.json"
    sentinel = "private-test-sentinel-never-log"
    (tmp_path / "credential.json").write_text(
        json.dumps({"email": "test@example.test", "token": sentinel})
    )
    requests = []

    def handler(request):
        requests.append(request)
        assert request.method == "GET"
        if request.url.host == "makegrigorev.atlassian.net":
            assert "Authorization" not in request.headers
            return httpx.Response(200, json={"cloudId": "00000000-0000-0000-0000-000000000001"})
        assert request.url.host == "api.atlassian.com"
        if request.url.path.endswith("mypermissions"):
            return httpx.Response(
                200,
                json={
                    "permissions": {
                        k: {"havePermission": True}
                        for k in ("BROWSE_PROJECTS", "CREATE_ISSUES", "ADD_COMMENTS")
                    }
                },
            )
        if request.url.path.endswith("project/KAN"):
            if project_status != 200:
                return httpx.Response(
                    project_status,
                    json={"message": "Unauthorized; scope does not match " + sentinel},
                )
            return httpx.Response(200, json={"id": "10000", "key": "KAN", "name": "OpsPilot Test"})
        assert request.url.path.endswith("issue/createmeta/KAN/issuetypes")
        return httpx.Response(
            200, json={"issueTypes": [{"id": "10001", "name": "Task", "subtask": False}]}
        )

    original = httpx.Client
    monkeypatch.setattr(
        module.httpx,
        "Client",
        lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs),
    )
    assert module.main() == (0 if expected else 1)
    stdout = capsys.readouterr().out
    assert sentinel not in stdout
    report = module.REPORT.read_text()
    assert sentinel not in report
    assert json.loads(report)["credential_authenticated"] is True
    assert json.loads(report)["passed"] is expected
    assert len(requests) == (4 if expected else 3)

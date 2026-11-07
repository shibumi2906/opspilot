"""Assemble measured local evidence; never promote the deferred staging gate."""

import json
import re
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path("docs/full/evidence/f19")


def read(name):
    return json.loads((ROOT / name).read_text(encoding="utf-8-sig"))


def scan(name):
    data = read("security/" + name + "-image.json")
    items = [v for r in data.get("Results", []) for v in (r.get("Vulnerabilities") or [])]
    counts = {
        s: sum(v["Severity"] == s for v in items)
        for s in ("CRITICAL", "HIGH", "MEDIUM", "LOW", "UNKNOWN")
    }
    assert counts["CRITICAL"] == counts["HIGH"] == 0
    return {"raw_counts": counts, "image_id": data["Metadata"]["ImageID"]}


regression = Path(".tools/f19-regression-final.log").read_text(encoding="utf-8-sig")
native = Path(".tools/f19-native-patched-final.log").read_text(encoding="utf-8-sig")
assert "527 passed, 74 skipped in 982.35s" in regression
assert "287 passed in 76.06s" in native
assert "Success: no issues found in 150 source files" in native
assert re.search(r"1 passed \(11\.9s\)", native)
browser = read("browser.json")["stats"]
assert (browser["expected"], browser["unexpected"], browser["skipped"], browser["flaky"]) == (
    1,
    0,
    0,
    0,
)
asvs, source, runtime, inventory = (
    read(n)
    for n in (
        "asvs-baseline-check.json",
        "source-image-match.json",
        "runtime-secret-check.json",
        "inventory.json",
    )
)
assert asvs["passed"] and asvs["protected_requirements"] == 253
assert source["passed"] and runtime["passed"]
assert read("mvp-final.json")["mvp_volume_content_unchanged"]
assert read("dev-health.json")["status"] == "ready"
assert inventory["dev_runtime"]["schema"] == "0019_adapters"
app, prometheus = scan("app"), scan("prometheus")
assert app["image_id"] == inventory["new_images"]["opspilot-full/app:f19"]
assert prometheus["image_id"] == inventory["new_images"]["opspilot-full/prometheus:f19"]
assert all(not r.get("vulns") for r in read("security/python-audit.json")["dependencies"])
assert read("security/npm-audit.json")["metadata"]["vulnerabilities"]["total"] == 0
modules = (ROOT / "security/prometheus-modules.txt").read_text()
assert "golang.org/x/net\tv0.62.0" in modules
result = {
    "stage": "F19",
    "stage_status": "blocked",
    "local_part": "complete",
    "observed_at_utc": datetime.now(UTC).isoformat(),
    "base": "61dfdfd",
    "commit_subject": "feat(full): implement local F19 Prometheus reads",
    "authorization": "User explicitly authorized local part and deferred staging target/credentials",
    "staging_live_gate": "OPEN",
    "full_pilot": "NOT_MET",
    "whole_ASVS_L2": "NOT_MET",
    "schemas": {"isolated_test": "0020_prometheus", "accepted_dev": "0019_adapters"},
    "checks": {
        "legacy_regression": {
            "passed": 527,
            "dedicated_skips": 74,
            "seconds": 982.35,
            "snapshot_ref": "regression/images.json",
        },
        "final_patched_native": {
            "passed": 287,
            "unit": 257,
            "native_contracts": 30,
            "seconds": 76.06,
            "failed": 0,
            "log": ".tools/f19-native-patched-final.log",
        },
        "real_oidc_browser": {
            "passed": 1,
            "failed": 0,
            "skipped": 0,
            "flaky": 0,
            "seconds": 11.9,
            "ref": "browser.json",
            "paid_model_cost_usd": 0,
        },
        "static": {"ruff": True, "format_python_files": 231, "mypy_source_files": 150},
        "source_image_match": {"passed": True, "app": 150, "tests": 81, "migrations": 21},
        "asvs": asvs,
        "runtime_secret_mounts": runtime,
        "artifact_secrets": read("artifact-secret-check.json"),
        "supply_chain": {
            "local_high_critical_gate_passed": True,
            "app": app,
            "prometheus": prometheus,
            "python_npm_audit": True,
            "upstream_high_occurrences_fixed": 2,
            "upstream_report": "security/upstream-prometheus-image.json",
            "fix": "checksum-pinned upstream3.16.0; x/net0.62.0; supported static-only build; no promtool/UI",
            "ignored_findings": 0,
            "nonblocking_raw_findings_retained": True,
        },
        "preservation": {
            "mvp": True,
            "f18_six_image_tags": True,
            "dev_ready": True,
            "dev_not_migrated_or_seeded": True,
            "test_profiles_stopped": True,
        },
    },
    "external_activity": {
        "paid_calls": 0,
        "vendor_writes": 0,
        "remote_CI": False,
        "push": False,
        "production_deployment": False,
        "public_source_advisory_downloads": True,
    },
    "limits": [
        "Local generated series stay synthetic even on a real patched Prometheus server.",
        "Authorized staging endpoint/credentials/tenant mapping and actual staging version/MCP/UI smoke remain absent by user choice.",
        "Native Basic Auth has no label-level RLS; staging upstream isolation or trusted gateway needs review.",
        "Raw MEDIUM(zlib)/UNKNOWN(x/crypto) retained; scoped HIGH/CRITICAL0 does not imply full ASVS compliance.",
        "Main Full remains accepted F18/schema0019; F19 code/schema/images validated only in isolated tests.",
        "Test counts overlap. Legacy regression preceded final Prometheus-only/fact-format refinements; final native snapshot and legacy-format unit cover them.",
        "F20/F21/F22/F23/F24 not started; no load/soak/real-holdout/production recovery or whole-norm closure.",
    ],
}
(ROOT / "checks.json").write_text(
    json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
)
print("F19 local measurements recorded; overall blocked, staging/live OPEN, whole L2 NOT_MET")

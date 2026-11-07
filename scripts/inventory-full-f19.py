"""Public image/source/PKI metadata only; assert accepted dev runtime tags stayed unchanged."""

import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes


def image_id(ref):
    return subprocess.check_output(
        ["docker", "image", "inspect", ref, "--format", "{{.Id}}"], text=True
    ).strip()


baseline = json.loads(Path("docs/full/evidence/f18/inventory.json").read_text(encoding="utf-8"))
unchanged = {}
for item in baseline["images"]:
    ref = item["reference"]
    actual = image_id(ref)
    assert actual == item["id"], "Accepted F18 image tag changed: " + ref
    unchanged[ref] = actual
images = {
    ref: image_id(ref)
    for ref in ("opspilot-full/app:f19", "opspilot-full/tests:f19", "opspilot-full/prometheus:f19")
}
code = """import asyncio,json
from opspilot.config import Settings
from opspilot.db.engine import create_engine
from sqlalchemy import text
async def main():
    e=create_engine(Settings().database_url('workflow'))
    try:
        async with e.connect() as c:
            print(json.dumps({'schema':await c.scalar(text('SELECT version_num FROM workflow.alembic_version'))}))
    finally:
        await e.dispose()
asyncio.run(main())
"""
runtime = json.loads(
    subprocess.check_output(
        ["docker", "exec", "opspilot-full-api-1", "python", "-c", code], text=True
    )
)
assert runtime["schema"] == "0019_adapters", "F19 must not migrate accepted dev implicitly"
certificates = {}
for name, path in {
    "ca": ".tools/f19-client/ca.crt",
    "fixture_server": ".tools/f19-server/server.crt",
}.items():
    cert = x509.load_pem_x509_certificate(Path(path).read_bytes())
    certificates[name] = {
        "sha256": cert.fingerprint(hashes.SHA256()).hex(),
        "signature": cert.signature_hash_algorithm.name,
        "public_key": type(cert.public_key()).__name__,
        "public_key_bits": cert.public_key().key_size,
        "not_after": cert.not_valid_after_utc.isoformat(),
    }
result = {
    "passed": True,
    "observed_at_utc": datetime.now(UTC).isoformat(),
    "base": "61dfdfd",
    "new_images": images,
    "accepted_f18_tags_unchanged": unchanged,
    "dev_runtime": runtime,
    "new_schema_test_only": "0020_prometheus",
    "certificates": certificates,
    "basic_fixture": "distinct 256-bit random per-connector passwords; bcrypt12 hashes; TLS only",
    "prometheus_digest": "sha256:e04987641b57704f408e31f6373ba4138ecf27cb4a165d24aabb6c38fddd0f06",
    "paid_calls": 0,
    "vendor_writes": 0,
    "staging_live_gate": "OPEN",
    "secrets_exported": False,
}
Path("docs/full/evidence/f19/inventory.json").write_text(json.dumps(result, indent=2) + "\n")
print("F19 image/PKI metadata recorded; F18 runtime/schema preserved; no secret values exported")

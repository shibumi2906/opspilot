"""Real TLS manager ACL, rotation, revoke, seal, restart and encrypted recovery evidence.

Only metadata reaches the report. Recovery material remains in ignored local storage.
"""

import importlib
import ipaddress
import json
import secrets
import ssl
import time
from datetime import UTC, datetime
from pathlib import Path

import jwt
import httpx
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from opspilot.security.keys import version
from opspilot.security.manager import BaoGrantKeys, ManagerUnavailable

m = importlib.import_module("setup-full-f17-manager")
checks = []


def passed(name: str) -> None:
    checks.append(name)


def ready(c, token):
    for _ in range(30):
        r = c.get("/v1/sys/health", headers={"X-Vault-Token": token})
        if r.status_code == 200:
            return
        time.sleep(1)
    raise RuntimeError("Manager leader did not become ready")


def restore_fresh(snapshot: bytes, original: dict, expected: str) -> None:
    config = json.loads((m.PRIVATE / "compose.json").read_text())
    config["name"] = "opspilot-full-test-f17-restore-" + secrets.token_hex(3)
    # Fresh volume and isolated DNS for every recovery drill, even on repeated runs.
    # Explicit non-overlapping private subnet avoids the exhausted default pools.
    existing_ids = m.docker("network", "ls", "--format", "{{.ID}}").split()
    existing = json.loads(m.docker("network", "inspect", *existing_ids))
    ranges = [ipaddress.ip_network(item["Subnet"]) for network in existing
              for item in (network.get("IPAM", {}).get("Config") or []) if item.get("Subnet")]
    subnet = next(ipaddress.ip_network(f"10.243.{n}.0/24") for n in range(17, 255)
                  if not any(ipaddress.ip_network(f"10.243.{n}.0/24").overlaps(r)
                             for r in ranges if r.version == 4))
    network_name = config["name"] + "-isolated"
    m.docker("network", "create", "--subnet", str(subnet), network_name)
    config["networks"] = {"default": {"external": True, "name": network_name}}
    config["services"]["manager"]["ports"] = ["127.0.0.1:18201:8200"]
    compose = m.PRIVATE / "restore-compose.json"
    compose.write_text(json.dumps(config))
    for volume in ("manager-data", "manager-audit"):
        m.docker("volume", "create", config["name"] + "_" + volume)
    m.docker("run", "--rm", "--network", "none", "--user", "0", "--entrypoint", "chown",
        "-v", config["name"] + "_manager-data:/data",
        "-v", config["name"] + "_manager-audit:/audit", m.IMAGE, "100:1000", "/data", "/audit")
    m.docker("compose", "-f", str(compose), "up", "-d")
    try:
        with httpx.Client(base_url="https://127.0.0.1:18201", trust_env=False,
                          verify=ssl.create_default_context(cafile=str(m.PRIVATE / "ca.crt")),
                          timeout=5) as c:
            for _ in range(30):
                try:
                    initialized = m.call(c, "GET", "sys/init")["initialized"]
                    break
                except httpx.HTTPError:
                    time.sleep(1)
            else:
                raise RuntimeError("Restore instance did not start")
            local_path = m.RECOVERY / (config["name"] + "-initialization.json")
            if not initialized:
                initial = m.call(c, "PUT", "sys/init", {"secret_shares": 1, "secret_threshold": 1})
                local_path.write_text(json.dumps(initial))
                m.call(c, "PUT", "sys/unseal", {"key": initial["keys"][0]})
                ready(c, initial["root_token"])
                response = c.post("/v1/sys/storage/raft/snapshot-force", content=snapshot,
                    headers={"X-Vault-Token": initial["root_token"]}, timeout=60)
                assert response.status_code in {200, 204}
            # Restart forces a clean read of restored encrypted storage and original seal keys.
            m.docker("compose", "-f", str(compose), "restart", "manager")
            for _ in range(30):
                try:
                    sealed = m.call(c, "GET", "sys/seal-status")["sealed"]
                    if sealed:
                        break
                except httpx.HTTPError:
                    pass
                time.sleep(1)
            for share in original["keys"][:2]:
                m.call(c, "PUT", "sys/unseal", {"key": share})
            ready(c, original["root_token"])
            public = m.call(c, "GET", "core/data/grants/public", token=original["root_token"])["data"]["data"]
            assert expected in public
            passed("fresh_instance_restores_encrypted_snapshot_and_original_key_identity")
    finally:
        m.docker("compose", "-f", str(compose), "stop")


def main() -> None:
    state = json.loads((m.RECOVERY / "initialization.json").read_text())
    root = state["root_token"]
    writer = BaoGrantKeys("https://127.0.0.1:18200", str(m.PRIVATE / "ca.crt"),
                          str(m.PRIVATE / "worker.token"))
    reader = BaoGrantKeys(writer.origin, writer.ca_file, str(m.PRIVATE / "mcp.token"))
    with m.client() as c:
        ready(c, root)
        original = m.call(c, "GET", "core/data/grants/active", token=root)["data"]["data"]
        ref, raw = writer.signing_key("grant-current")
        now = int(time.time())
        token = jwt.encode({"sub": "in-flight-job", "iat": now, "exp": now + 60}, raw,
                           algorithm="EdDSA", headers={"kid": ref.kid})
        assert jwt.decode(token, reader.verification_key(ref.kid), algorithms=["EdDSA"])["sub"] == "in-flight-job"
        passed("TLS_worker_sign_MCP_public_verify")
        try:
            reader.signing_key("grant-current")
            raise AssertionError("MCP read private signing material")
        except ManagerUnavailable:
            passed("MCP_private_key_ACL_denied")
        for role in ("worker", "mcp"):
            credential = (m.PRIVATE / (role + ".token")).read_text()
            for path in ("core/data/grants/active", "sys/policies/acl/f17-worker"):
                r = c.post("/v1/" + path, json={"data": {}}, headers={"X-Vault-Token": credential})
                assert r.status_code == 403
            passed(role + "_mutation_and_policy_escalation_denied")
        sentinel = "F17_MANAGER_SENTINEL_NO_EXPORT_OR_AUDIT_RAW_7c45"
        for tenant in ("a", "b"):
            m.call(c, "POST", "core/data/tenants/" + tenant + "/probe", {"data": {"value": sentinel}}, root)
            credential = (m.PRIVATE / ("tenant-" + tenant + ".token")).read_text()
            own = c.get("/v1/core/data/tenants/" + tenant + "/probe", headers={"X-Vault-Token": credential})
            assert own.status_code == 200
            other = "b" if tenant == "a" else "a"
            assert c.get("/v1/core/data/tenants/" + other + "/probe", headers={"X-Vault-Token": credential}).status_code == 403
        passed("two_tenant_secret_ACLs")
        # Prepare verification overlap before publishing the new active immutable version.
        public = m.call(c, "GET", "core/data/grants/public", token=root)["data"]["data"]
        replacement = Ed25519PrivateKey.generate()
        kid = version("grant-current", replacement.public_key())
        next_version = secrets.randbelow(900000000) + 3
        public[kid] = replacement.public_key().public_bytes(serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo).decode()
        m.call(c, "POST", f"core/data/grants/private/{next_version}", {"options": {"cas": 0},
            "data": {"pem": replacement.private_bytes(serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8, serialization.NoEncryption()).decode()}}, root)
        m.call(c, "POST", "core/data/grants/public", {"data": public}, root)
        m.call(c, "POST", "core/data/grants/active", {"data": {**original, "grant-current": next_version}}, root)
        assert writer.signing_key("grant-current")[0].kid == kid
        jwt.decode(token, reader.verification_key(ref.kid), algorithms=["EdDSA"])
        passed("rotation_preserves_inflight_signature_and_uses_new_key")
        # Compromise: remove the old verification key, so even unexpired transport is denied.
        del public[ref.kid]
        m.call(c, "POST", "core/data/grants/public", {"data": public}, root)
        try:
            reader.verification_key(ref.kid)
            raise AssertionError("Revoked key accepted")
        except ManagerUnavailable:
            passed("compromised_key_revoke_denies_inflight")
        # Restore the trusted old public key during recovery, then safely roll back active config.
        old_key = serialization.load_pem_private_key(raw, password=None).public_key()
        public[ref.kid] = old_key.public_bytes(serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo).decode()
        m.call(c, "POST", "core/data/grants/public", {"data": public}, root)
        m.call(c, "POST", "core/data/grants/active", {"data": original}, root)
        assert writer.signing_key("grant-current")[0] == ref
        passed("reversible_safe_active_configuration")
        expired = m.call(c, "POST", "auth/token/create", {"policies": ["f17-mcp"],
            "no_default_policy": True, "ttl": "1s", "explicit_max_ttl": "1s", "renewable": False}, root)["auth"]["client_token"]
        time.sleep(2)
        assert c.get("/v1/core/data/grants/public", headers={"X-Vault-Token": expired}).status_code == 403
        passed("short_lived_access_expires")
        victim = m.call(c, "POST", "auth/token/create", {"policies": ["f17-worker"],
            "no_default_policy": True, "ttl": "60s"}, root)["auth"]["client_token"]
        m.call(c, "POST", "auth/token/revoke", {"token": victim}, root)
        assert c.get("/v1/core/data/grants/public", headers={"X-Vault-Token": victim}).status_code == 403
        passed("compromised_service_access_revoked")
        # Raft snapshot is already barrier-encrypted, then envelope-encrypted with a separate backup key.
        snapshot = c.get("/v1/sys/storage/raft/snapshot", headers={"X-Vault-Token": root}, timeout=30)
        assert snapshot.status_code == 200 and len(snapshot.content) > 100
        key_path = m.RECOVERY / "backup.key"
        if not key_path.exists():
            key_path.write_bytes(Fernet.generate_key())
        envelope = Fernet(key_path.read_bytes())
        backup = m.PRIVATE / "raft.snapshot.enc"
        backup.write_bytes(envelope.encrypt(snapshot.content))
        assert envelope.decrypt(backup.read_bytes()) == snapshot.content
        passed("encrypted_snapshot_with_separate_backup_key")
        restore_fresh(envelope.decrypt(backup.read_bytes()), state, ref.kid)
        m.call(c, "PUT", "sys/seal", token=root)
        try:
            writer.signing_key("grant-current")
            raise AssertionError("Sealed manager used a fallback key")
        except ManagerUnavailable:
            passed("seal_outage_fails_closed_without_file_fallback")
        m.docker("compose", "-f", str(m.PRIVATE / "compose.json"), "restart", "manager")
        for _ in range(30):
            try:
                if m.call(c, "GET", "sys/seal-status")["sealed"]:
                    break
            except Exception:
                pass
            time.sleep(1)
        for share in state["keys"][:2]:
            m.call(c, "PUT", "sys/unseal", {"key": share})
        ready(c, root)
        assert writer.signing_key("grant-current")[0] == ref
        passed("restart_threshold_unseal_recovers_same_keys")
        audit = m.docker("compose", "-f", str(m.PRIVATE / "compose.json"), "exec", "-T",
                         "manager", "cat", "/bao/audit/audit.json")
        assert sentinel not in audit and raw.decode() not in audit
        assert root not in audit and victim not in audit
        assert '"request"' in audit and '"response"' in audit
        passed("protected_audit_sentinel_and_credentials_HMAC_redacted")
    image_id = m.docker("inspect", m.PROJECT + "-manager-1", "--format", "{{.Image}}").strip()
    version_text = m.docker("compose", "-f", str(m.PRIVATE / "compose.json"), "exec", "-T", "manager", "bao", "version").strip()
    proof = json.loads(m.docker("compose", "-f", str(m.PRIVATE / "compose.json"), "exec", "-T", "manager", "cat", "/usr/share/opspilot-manager/f17-patch-proof.json"))
    Path("docs/full/evidence/f17/security/manager-patch-proof.json").write_text(json.dumps(proof, indent=2) + "\n")
    report = {"profile": "local-native-TLS-OpenBao-2.7.2-opspilot-f17.1-Raft", "checks": checks,
              "executed_at_utc": datetime.now(UTC).isoformat(), "source_base": "6330f32",
              "runtime_image_id": image_id, "runtime_version": version_text,
              "passed": len(checks), "full_L2": "NOT_MET", "secrets_in_report": False,
              "restore_to_fresh_instance": True}
    Path("docs/full/evidence/f17/manager.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"manager_checks_passed": len(checks)}))


if __name__ == "__main__":
    main()

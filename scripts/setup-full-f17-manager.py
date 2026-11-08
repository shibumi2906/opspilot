"""Provision an isolated, non-dev, TLS OpenBao. Private state stays ignored; never printed.

Run from Ops after the MVP isolation gate. Existing initialization is preserved.
"""

import ipaddress
import argparse
import json
import ssl
import shutil
import subprocess
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ed25519, rsa
from cryptography.x509.oid import NameOID

from opspilot.security.keys import version

ROOT = Path.cwd()
PRIVATE = ROOT / ".tools/f17-manager"
RECOVERY = ROOT / ".tools/f17-recovery"
IMAGE = "opspilot-full/manager:f17"
PROJECT = "opspilot-full-test-f17-manager-r2"
PORT = 18200
APPLICATION_NETWORKS: tuple[str, ...] | None = None
EXTERNAL_NETWORK: str | None = None


def local_profile() -> None:
    global PRIVATE, RECOVERY, PROJECT, PORT
    PRIVATE = ROOT / ".tools/f17-manager-dev"
    RECOVERY = ROOT / ".tools/f17-recovery-dev"
    PROJECT = "opspilot-full"
    PORT = 18202


def docker(*args: str) -> str:
    result = subprocess.run(["docker", *args], capture_output=True, text=True, check=False)
    if result.returncode:
        raise RuntimeError("Manager container operation failed")
    return result.stdout


def prepare() -> None:
    if not PRIVATE.exists():
        PRIVATE.mkdir(parents=True)
        RECOVERY.mkdir(parents=True, exist_ok=True)
        key = rsa.generate_private_key(public_exponent=65537, key_size=3072)
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "F17 local manager CA")])
        now = datetime.now(UTC)
        ca = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
              .public_key(key.public_key()).serial_number(x509.random_serial_number())
              .not_valid_before(now - timedelta(minutes=5)).not_valid_after(now + timedelta(days=90))
              .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
              .sign(key, hashes.SHA384()))
        server = rsa.generate_private_key(public_exponent=65537, key_size=3072)
        cert = (x509.CertificateBuilder().subject_name(x509.Name([
            x509.NameAttribute(NameOID.COMMON_NAME, "manager")])).issuer_name(name)
            .public_key(server.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(minutes=5)).not_valid_after(now + timedelta(days=30))
            .add_extension(x509.SubjectAlternativeName([
                x509.DNSName("manager"), x509.DNSName("localhost"),
                x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]), critical=False)
            .sign(key, hashes.SHA384()))
        for file, value in (("ca.crt", ca.public_bytes(serialization.Encoding.PEM)),
                            ("server.crt", cert.public_bytes(serialization.Encoding.PEM)),
                            ("server.key", server.private_bytes(serialization.Encoding.PEM,
                                serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))):
            (PRIVATE / file).write_bytes(value)
        (RECOVERY / "ca.key").write_bytes(key.private_bytes(serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
        (PRIVATE / "config.json").write_text(json.dumps({
            "ui": False,
            "storage": {"raft": {"path": "/bao/data", "node_id": "f17-manager"}},
            "api_addr": "https://manager:8200", "cluster_addr": "https://manager:8201",
            "listener": {"tcp": {"address": "0.0.0.0:8200", "tls_min_version": "tls12",
                "tls_cert_file": "/run/manager/server.crt", "tls_key_file": "/run/manager/server.key"}},
            "audit": [{"file": {"protected": {"options": {
                "file_path": "/bao/audit/audit.json", "log_raw": "false"}}}}],
            "log_level": "warn"}), encoding="utf-8")
    runtime_keys = PRIVATE / "service-private"
    runtime_keys.mkdir(exist_ok=True)
    for slot in ("current", "next"):
        shutil.copyfile(ROOT / ".tools/service-keys/private" / (slot + ".pem"),
                        runtime_keys / (slot + ".pem"))
    # HCL keeps both audit labels unambiguous across the manager's JSON parser versions.
    (PRIVATE / "config.hcl").write_text('''
ui = false
storage "raft" { path = "/bao/data" node_id = "f17-manager" }
api_addr = "https://manager:8200"
cluster_addr = "https://manager:8201"
listener "tcp" {
 address = "0.0.0.0:8200"
 tls_min_version = "tls12"
 tls_cert_file = "/run/manager/server.crt"
 tls_key_file = "/run/manager/server.key"
}
audit "file" "protected" {
 options = { file_path = "/bao/audit/audit.json", log_raw = "false" }
}
log_level = "warn"
''', encoding="utf-8")
    compose = {"name": PROJECT, "services": {"manager": {
        "image": IMAGE, "command": ["server", "-config=/run/manager/config.hcl"],
        "cap_drop": ["ALL"], "security_opt": ["no-new-privileges:true"],
        "read_only": True, "mem_limit": "512m", "memswap_limit": "512m", "pids_limit": 128,
        "ports": [f"127.0.0.1:{PORT}:8200"],
        "volumes": [f"{PRIVATE.as_posix()}:/run/manager:ro", "manager-data:/bao/data", "manager-audit:/bao/audit"],
        "tmpfs": ["/tmp:rw,noexec,nosuid,size=16m"]}},
        "volumes": {"manager-data": {}, "manager-audit": {}}}
    if EXTERNAL_NETWORK:
        compose["networks"] = {"default": {"external": True, "name": EXTERNAL_NETWORK}}
    (PRIVATE / "compose.json").write_text(json.dumps(compose), encoding="utf-8")
    docker("volume", "create", PROJECT + "_manager-data")
    docker("volume", "create", PROJECT + "_manager-audit")
    docker("run", "--rm", "--network", "none", "--user", "0", "--entrypoint", "chown",
           "-v", PROJECT + "_manager-data:/data", "-v", PROJECT + "_manager-audit:/audit",
           IMAGE, "100:1000", "/data", "/audit")
    docker("compose", "-f", str(PRIVATE / "compose.json"), "up", "-d")
    container = PROJECT + "-manager-1"
    connected = json.loads(docker("inspect", container, "--format", "{{json .NetworkSettings.Networks}}"))
    # Only the manager joins isolated application networks. Application services
    # never join its common network, where duplicate MCP aliases would collide.
    application_networks = APPLICATION_NETWORKS
    if application_networks is None:
        application_networks = (() if PROJECT == "opspilot-full" else
            ("opspilot-full-test-f17-manager_default", "opspilot-full-test-f17-r1_default"))
    for network in application_networks:
        if network not in connected:
            docker("network", "connect", "--alias", "manager", network, container)


def client() -> httpx.Client:
    return httpx.Client(base_url=f"https://127.0.0.1:{PORT}", trust_env=False,
                        verify=ssl.create_default_context(cafile=str(PRIVATE / "ca.crt")), timeout=5)


def call(c: httpx.Client, method: str, path: str, data: dict | None = None,
         token: str | None = None) -> dict:
    response = c.request(method, "/v1/" + path, json=data,
                         headers={"X-Vault-Token": token} if token else {},
                         timeout=60 if path == "sys/init" and method == "PUT" else 5)
    if response.status_code not in {200, 204}:
        raise RuntimeError("Manager provisioning request denied")
    return response.json() if response.content else {}


def bootstrap() -> None:
    prepare()
    with client() as c:
        for _ in range(45):
            try:
                initialized = call(c, "GET", "sys/init")["initialized"]
                break
            except (httpx.HTTPError, RuntimeError):
                time.sleep(1)
        else:
            raise RuntimeError("Manager did not become ready")
        state_path = RECOVERY / "initialization.json"
        if not initialized:
            state = call(c, "PUT", "sys/init", {"secret_shares": 3, "secret_threshold": 2})
            state_path.write_text(json.dumps(state), encoding="utf-8")
        state = json.loads(state_path.read_text())
        if call(c, "GET", "sys/seal-status")["sealed"]:
            for share in state["keys"][:2]:
                call(c, "PUT", "sys/unseal", {"key": share})
        for _ in range(30):
            if c.get("/v1/sys/health").status_code == 200:
                break
            time.sleep(1)
        else:
            raise RuntimeError("Manager leader not ready after unseal")
        root = state["root_token"]
        mounts = call(c, "GET", "sys/mounts", token=root)
        if "core/" not in mounts:
            call(c, "POST", "sys/mounts/core", {"type": "kv", "options": {"version": "2"}}, root)
        audits = call(c, "GET", "sys/audit", token=root)
        if "protected/" not in audits.get("data", audits):
            raise RuntimeError("Protected declarative audit required")
        # Provision once. Subsequent setup never overwrites existing manager signing keys.
        for _ in range(25):
            exists = c.get("/v1/core/data/grants/active", headers={"X-Vault-Token": root})
            if exists.status_code in {200, 404}:
                break
            time.sleep(0.2)
        if exists.status_code == 404:
            public = {}
            for index, slot in enumerate(("grant-current", "grant-next"), 1):
                if PROJECT == "opspilot-full":
                    # Import existing Full identities; setup never rotates existing keys.
                    private = serialization.load_pem_private_key(
                        (ROOT / ".tools/service-keys/private" / (slot + ".pem")).read_bytes(),
                        password=None)
                    if not isinstance(private, ed25519.Ed25519PrivateKey):
                        raise RuntimeError("Preserved Full grant key must be Ed25519")
                else:
                    private = ed25519.Ed25519PrivateKey.generate()
                kid = version(slot, private.public_key())
                public[kid] = private.public_key().public_bytes(serialization.Encoding.PEM,
                    serialization.PublicFormat.SubjectPublicKeyInfo).decode()
                call(c, "POST", f"core/data/grants/private/{index}", {"options": {"cas": 0},
                     "data": {"pem": private.private_bytes(serialization.Encoding.PEM,
                        serialization.PrivateFormat.PKCS8, serialization.NoEncryption()).decode()}}, root)
            call(c, "POST", "core/data/grants/public", {"data": public}, root)
            call(c, "POST", "core/data/grants/active", {"data": {"grant-current": 1, "grant-next": 2}}, root)
        elif exists.status_code != 200:
            raise RuntimeError("Manager key state unavailable")
        policies = {
            "worker": 'path "core/data/grants/*" { capabilities = ["read"] }',
            "mcp": 'path "core/data/grants/public" { capabilities = ["read"] }',
            "tenant-a": 'path "core/data/tenants/a/*" { capabilities = ["read"] }',
            "tenant-b": 'path "core/data/tenants/b/*" { capabilities = ["read"] }',
        }
        for role, policy in policies.items():
            call(c, "PUT", "sys/policies/acl/f17-" + role, {"policy": policy}, root)
            # Short-lived access; operator replaces tokens explicitly. No renewable root in runtime.
            result = call(c, "POST", "auth/token/create", {"policies": ["f17-" + role],
                "no_default_policy": True, "ttl": "1h", "explicit_max_ttl": "1h",
                "renewable": False, "display_name": "f17-" + role}, root)
            (PRIVATE / (role + ".token")).write_text(result["auth"]["client_token"], encoding="utf-8")
    print("F17 manager ready: native TLS, encrypted persistent storage, ACL and protected audit; no secrets printed")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--local", action="store_true", help="Independent manager in opspilot-full; preserve Full key identities")
    if parser.parse_args().local:
        local_profile()
    bootstrap()

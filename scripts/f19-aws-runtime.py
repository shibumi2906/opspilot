"""Configure the authorized disposable host; no credentials printed or committed."""

import base64
import importlib.util
import ipaddress
import json
import secrets
import shutil
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid5

import bcrypt
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
spec = importlib.util.spec_from_file_location("aws_stage", ROOT / "scripts/f19-aws-staging.py")
stage = importlib.util.module_from_spec(spec)
spec.loader.exec_module(stage)
PRIVATE = stage.PRIVATE
UPLOAD = PRIVATE / "upload"
CLIENT = PRIVATE / "client"


def ssh_args():
    state = json.loads(stage.LEDGER.read_text())
    return [
        "-i",
        str(PRIVATE / "ssh-key"),
        "-o",
        "BatchMode=yes",
        "-o",
        "StrictHostKeyChecking=yes",
        "-o",
        "UserKnownHostsFile=" + str(PRIVATE / "known_hosts"),
        "-o",
        "ConnectTimeout=10",
    ], "ec2-user@" + state["address"]


def pin_host():
    state = json.loads(stage.LEDGER.read_text())
    instance = stage.aws(
        "opspilot-admin-setup",
        "ec2",
        "describe-instances",
        instance_ids=state["resources"]["instance"],
    )["Reservations"][0]["Instances"][0]
    if instance["State"]["Name"] != "running":
        raise RuntimeError("Wait for running instance")
    state["address"] = str(ipaddress.IPv4Address(instance["PublicIpAddress"]))
    state["launched_at"] = instance["LaunchTime"]
    stage.save(state)
    # SSH public host fingerprint is independently checked against AWS console.
    output = stage.aws(
        "opspilot-admin-setup",
        "ec2",
        "get-console-output",
        instance_id=instance["InstanceId"],
        latest=True,
    )["Output"]
    try:
        output = base64.b64decode(output, validate=True).decode(errors="replace")
    except (ValueError, UnicodeError):
        pass
    scan = stage.run(["ssh-keyscan", "-T", "10", "-t", "ed25519", state["address"]])
    keyfile = PRIVATE / "host-candidate.pub"
    keyfile.write_text(scan)
    fingerprint = stage.run(["ssh-keygen", "-l", "-f", str(keyfile)]).split()[1]
    if fingerprint not in output:
        raise RuntimeError("SSH key not verified in AWS console output; do not bypass")
    (PRIVATE / "known_hosts").write_text(scan)
    print("SSH host key independently pinned against AWS console")


def write_private_key(path, key):
    path.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )


def prepare_runtime():
    from tests.f19_cases import CASES

    state = json.loads(stage.LEDGER.read_text())
    for folder in (UPLOAD, CLIENT):
        folder.mkdir(exist_ok=True)
    if (UPLOAD / "web.json").exists():
        raise RuntimeError("Runtime material exists; reuse explicitly, never rotate implicitly")
    scope = {k: CASES[0][k] for k in ("tenant_id", "customer_id", "integration_id")}
    now = datetime.now(UTC)
    ca_key = rsa.generate_private_key(public_exponent=65537, key_size=3072)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "OpsPilot F19 AWS staging CA")])
    ca = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(ca_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5))
        .not_valid_after(now + timedelta(days=2))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), True)
        .sign(ca_key, hashes.SHA384())
    )
    write_private_key(PRIVATE / "ca.key", ca_key)
    (CLIENT / "ca.crt").write_bytes(ca.public_bytes(serialization.Encoding.PEM))
    key = rsa.generate_private_key(public_exponent=65537, key_size=3072)
    cert = (
        x509.CertificateBuilder()
        .subject_name(
            x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "OpsPilot staging Prometheus")])
        )
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5))
        .not_valid_after(now + timedelta(days=1))
        .add_extension(
            x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address(state["address"]))]),
            False,
        )
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), True)
        .sign(ca_key, hashes.SHA384())
    )
    (UPLOAD / "server.crt").write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    write_private_key(UPLOAD / "server.key", key)
    credential = {"username": "opspilot_staging", "password": secrets.token_hex(32)}
    (PRIVATE / "credential.json").write_text(json.dumps(credential))
    web = {
        "tls_server_config": {
            "cert_file": "/opt/opspilot-f19/server.crt",
            "key_file": "/opt/opspilot-f19/server.key",
            "min_version": "TLS12",
        },
        "basic_auth_users": {
            credential["username"]: bcrypt.hashpw(
                credential["password"].encode(), bcrypt.gensalt()
            ).decode()
        },
    }
    (UPLOAD / "web.json").write_text(json.dumps(web))
    (UPLOAD / "observer.json").write_text(
        json.dumps({"scope": scope, "targets": {"primary": 8080, "replica": 8081}})
    )
    (UPLOAD / "prometheus.json").write_text(
        json.dumps(
            {
                "global": {"scrape_interval": "5s", "scrape_timeout": "1s"},
                "scrape_configs": [
                    {
                        "job_name": "opspilot",
                        "sample_limit": 20,
                        "static_configs": [{"targets": ["127.0.0.1:9100"]}],
                    }
                ],
            }
        )
    )
    shutil.copyfile(PRIVATE / "prometheus", UPLOAD / "prometheus")
    shutil.copyfile(ROOT / "infra/prometheus/staging-observer.py", UPLOAD / "observer.py")
    registration = {
        **CASES[0],
        "connector_id": str(uuid5(UUID(scope["tenant_id"]), "f19-aws-staging-v1")),
        "origin": "https://" + state["address"] + ":8443",
        "addresses": [state["address"]],
        "ca_file": "/run/prometheus-client/ca.crt",
        "targets": ["primary", "replica"],
        "deployment": "staging",
        "dataset": "observed",
        "allow_private": False,
        "authorization_ref": "owner-approved AWS F19 <=24h <=USD5; " + state["run"],
    }
    (CLIENT / "registry.json").write_text(json.dumps([registration]))
    units = {
        "primary": "python3 /opt/opspilot-f19/observer.py service 8080",
        "replica": "python3 /opt/opspilot-f19/observer.py service 8081",
        "observer": "python3 /opt/opspilot-f19/observer.py observer "
        "/opt/opspilot-f19/observer.json",
        "prometheus": "/opt/opspilot-f19/prometheus "
        "--config.file=/opt/opspilot-f19/prometheus.json "
        "--web.config.file=/opt/opspilot-f19/web.json --web.listen-address=:8443 "
        "--storage.tsdb.path=/var/lib/opspilot-f19/prometheus --storage.tsdb.retention.time=1h "
        "--storage.tsdb.retention.size=128MB --query.max-concurrency=4 --query.max-samples=2000 "
        "--query.timeout=1s --web.max-connections=32",
    }
    for unit, command in units.items():
        (UPLOAD / (unit + ".service")).write_text(
            "[Unit]\nAfter=network.target\n[Service]\nUser=opspilot\nGroup=opspilot\nExecStart="
            + ("/usr/bin/" if command.startswith("python3") else "")
            + command
            + "\nRestart=on-failure\nNoNewPrivileges=yes\nProtectSystem=strict\nProtectHome=yes\n"
            "PrivateTmp=yes\nReadWritePaths=/var/lib/opspilot-f19\nMemoryMax=256M\nCPUQuota=50%\n"
            "LimitNOFILE=1024\n[Install]\nWantedBy=multi-user.target\n",
            newline="\n",
        )
    deadline = datetime.fromisoformat(state["launched_at"]) + timedelta(hours=23)
    (UPLOAD / "install.sh").write_text(
        "#!/bin/bash\nset -eu\n"
        "cp /home/ec2-user/f19-upload/* /opt/opspilot-f19/\n"
        "chown -R root:opspilot /opt/opspilot-f19\nchmod 750 /opt/opspilot-f19\n"
        "chmod 640 /opt/opspilot-f19/*\nchmod 750 /opt/opspilot-f19/prometheus\n"
        + "\n".join(
            f"cp /opt/opspilot-f19/{u}.service /etc/systemd/system/f19-{u}.service" for u in units
        )
        + "\ncat > /etc/systemd/system/f19-deadline.service <<'UNIT'\n"
        "[Service]\nType=oneshot\nExecStart=/usr/sbin/shutdown -P now\nUNIT\n"
        "cat > /etc/systemd/system/f19-deadline.timer <<'UNIT'\n[Timer]\nOnCalendar="
        + deadline.strftime("%Y-%m-%d %H:%M:%S UTC")
        + "\nPersistent=true\n[Install]\nWantedBy=timers.target\nUNIT\n"
        "systemctl daemon-reload\nsystemctl enable --now f19-deadline.timer\n"
        + "systemctl enable --now "
        + " ".join("f19-" + u for u in units)
        + "\nsystemctl is-active "
        + " ".join("f19-" + u for u in units)
        + "\nsystemctl list-timers f19-deadline.timer --no-pager\n",
        newline="\n",
    )
    print("Prepared TLS, read credential, observed registration and bounded units; values withheld")


def deploy():
    options, target = ssh_args()
    wanted = json.loads(stage.LEDGER.read_text())["binary_sha256"]
    actual = stage.run(
        [
            "ssh",
            *options,
            target,
            "if test -f /home/ec2-user/f19-upload/prometheus; then "
            "sha256sum /home/ec2-user/f19-upload/prometheus; else echo missing; fi",
        ]
    ).split()[0]
    if actual != wanted:
        stage.run(
            [
                "scp",
                "-C",
                *options,
                str(UPLOAD / "prometheus"),
                target + ":/home/ec2-user/f19-upload/prometheus",
            ]
        )
    files = [str(p) for p in UPLOAD.iterdir() if p.is_file() and p.name != "prometheus"]
    stage.run(["scp", *options, *files, target + ":/home/ec2-user/f19-upload/"])
    stage.run(["ssh", *options, target, "sudo systemctl stop f19-deadline.timer"])
    print(stage.run(["ssh", *options, target, "sudo bash /home/ec2-user/f19-upload/install.sh"]))


if __name__ == "__main__":
    {"pin": pin_host, "prepare": prepare_runtime, "deploy": deploy}[sys.argv[1]]()

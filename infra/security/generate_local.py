"""Generate only an isolated synthetic TLS/MFA lab; never modifies MVP or OS trust."""

import json
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ed25519, rsa
from cryptography.fernet import Fernet
from cryptography.x509.oid import NameOID

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / ".tools/security-local"
if OUT.exists():
    raise SystemExit("Existing lab credentials preserved. Use existing compose; do not regenerate.")
OUT.mkdir(parents=True, mode=0o700)
(OUT / "service-private").mkdir()
(OUT / "service-public").mkdir()
service_key = ed25519.Ed25519PrivateKey.generate()
(OUT / "service-private/current.pem").write_bytes(
    service_key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    )
)
(OUT / "service-public/keys.json").write_text(
    json.dumps(
        {
            "current": service_key.public_key()
            .public_bytes(
                serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
            )
            .decode()
        }
    )
)

grant_ring = {}
for kid in ("grant-current", "grant-next"):
    grant_key = ed25519.Ed25519PrivateKey.generate()
    (OUT / ("service-private/" + kid + ".pem")).write_bytes(
        grant_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    grant_ring[kid] = (
        grant_key.public_key()
        .public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
        .decode()
    )
(OUT / "service-public/grants.json").write_text(json.dumps(grant_ring))
now = datetime.now(timezone.utc)


def key():
    return rsa.generate_private_key(public_exponent=65537, key_size=3072)


def save_key(name, k):
    (OUT / (name + ".key")).write_bytes(
        k.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )


ca_key = key()
ca_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "OpsPilot isolated local lab CA")])
ca = (
    x509.CertificateBuilder()
    .subject_name(ca_name)
    .issuer_name(ca_name)
    .public_key(ca_key.public_key())
    .serial_number(x509.random_serial_number())
    .not_valid_before(now - timedelta(minutes=5))
    .not_valid_after(now + timedelta(days=30))
    .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
    .sign(ca_key, hashes.SHA384())
)
save_key("ca", ca_key)
(OUT / "ca.crt").write_bytes(ca.public_bytes(serialization.Encoding.PEM))
for name in ["postgres", "api", "mcp", "app.opspilot.localhost", "idp.opspilot.localhost"]:
    k = key()
    cert = (
        x509.CertificateBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, name)]))
        .issuer_name(ca_name)
        .public_key(k.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5))
        .not_valid_after(now + timedelta(days=14))
        .add_extension(x509.SubjectAlternativeName([x509.DNSName(name)]), False)
        .add_extension(x509.ExtendedKeyUsage([x509.oid.ExtendedKeyUsageOID.SERVER_AUTH]), False)
        .sign(ca_key, hashes.SHA384())
    )
    save_key(name, k)
    (OUT / (name + ".crt")).write_bytes(cert.public_bytes(serialization.Encoding.PEM))
passwords = {
    n: secrets.token_hex(32)
    for n in ["migration", "workflow", "domain", "checkpoint", "identity", "admin", "user"]
}
(OUT / "credentials.json").write_text(json.dumps(passwords))
(OUT / "session.key").write_text(secrets.token_hex(48))
(OUT / "token.key").write_bytes(Fernet.generate_key())
app = "https://app.opspilot.localhost:8443"
issuer = "https://idp.opspilot.localhost:8543/realms/opspilot"
realm = json.loads((ROOT / "infra/identity/opspilot-realm.json").read_text())
realm.update(
    sslRequired="all",
    bruteForceProtected=True,
    failureFactor=5,
    waitIncrementSeconds=60,
    maxFailureWaitSeconds=900,
    minimumQuickLoginWaitSeconds=60,
    quickLoginCheckMilliSeconds=1000,
    passwordPolicy='length(15) and maxLength(128) and notUsername(undefined) and notEmail(undefined) and passwordHistory(5) and passwordBlacklist(common-passwords.txt) and maxAuthAge(0)',
    accessTokenLifespan=900,
    ssoSessionIdleTimeout=900,
    ssoSessionMaxLifespan=3600,
    eventsEnabled=True,
    adminEventsEnabled=True,
    adminEventsDetailsEnabled=False,
    eventsExpiration=604800,
    otpPolicyType="totp",
    otpPolicyAlgorithm="HmacSHA1",
    otpPolicyDigits=6,
    otpPolicyPeriod=30,
    otpPolicyLookAheadWindow=0,
    otpPolicyCodeReusable=False,
)
realm["browserFlow"] = "security-browser"
realm["authenticationFlows"] = [
    {
        "alias": "security-browser",
        "description": "Mandatory password and TOTP; no cookie bypass",
        "providerId": "basic-flow",
        "topLevel": True,
        "builtIn": False,
        "authenticationExecutions": [
            {
                "authenticator": "auth-username-password-form",
                "requirement": "REQUIRED",
                "priority": 10,
                "autheticatorFlow": False,
            },
            {
                "authenticator": "auth-otp-form",
                "requirement": "REQUIRED",
                "priority": 20,
                "autheticatorFlow": False,
            },
        ],
    }
]
realm["components"] = {
    "org.keycloak.keys.KeyProvider": [
        {
            "name": "rsa-generated",
            "providerId": "rsa-generated",
            "subType": "rsa",
            "config": {"priority": ["100"], "algorithm": ["RS256"], "keySize": ["4096"]},
        }
    ]
}
c = realm["clients"][0]
c["redirectUris"] = [app + "/auth/callback"]
c["webOrigins"] = [app]
c["defaultClientScopes"] = ["basic", "profile", "roles", "web-origins"]
c["optionalClientScopes"] = []
c["protocolMappers"] = [
    {
        "name": "mandatory-password-otp-assurance",
        "protocol": "openid-connect",
        "protocolMapper": "oidc-hardcoded-claim-mapper",
        "config": {
            "claim.name": "acr",
            "claim.value": "2",
            "jsonType.label": "String",
            "id.token.claim": "true",
            "access.token.claim": "true",
        },
    }
]
otps = {}
for u in realm["users"]:
    secret = secrets.token_hex(20)
    otps[u["username"]] = secret
    u["credentials"] = [
        {"type": "password", "value": passwords["user"], "temporary": False},
        {
            "type": "otp",
            "secretData": json.dumps({"value": secret}),
            "credentialData": json.dumps(
                {
                    "subType": "totp",
                    "digits": 6,
                    "counter": 0,
                    "period": 30,
                    "algorithm": "HmacSHA1",
                }
            ),
        },
    ]
    u["requiredActions"] = []
(OUT / "otp-fixtures.json").write_text(json.dumps(otps))
(OUT / "realm.json").write_text(json.dumps(realm))


# Every service receives only its own key; CA signing key is never mounted.
def mounts(*names):
    return [f"./{n}:/tls/{n}:ro" for n in names]


ca_mount = mounts("ca.crt")
common = {
    "APP_ENV": "test",
    "SECURITY_PROFILE": "hardened",
    "ALLOW_DEMO_SELF_APPROVAL": "false",
    "MAX_ACTOR_ACTIVE_RUNS": "8",
    "MAX_TENANT_ACTIVE_RUNS": "64",
    "MAX_GLOBAL_ACTIVE_RUNS": "128",
    "TLS_CA_FILE": "/tls/ca.crt",
    "APP_ORIGIN": app,
    "OIDC_ISSUER": issuer,
    "OIDC_INTERNAL_ISSUER": issuer,
    "MCP_URL": "https://mcp:8001/mcp",
    "OTEL_ENDPOINT": "",
    "JAEGER_URL": "",
    "SESSION_TTL_SECONDS": "900",
    "SESSION_IDLE_SECONDS": "300",
}


def dsn(role):
    user = "ops_" + role
    return (
        f"postgresql+psycopg://{user}:{passwords[role]}@postgres/opspilot_full_test?sslmode=verify-full&sslrootcert=/tls/ca.crt"
        + ("&options=-csearch_path%3Dcheckpoints" if role == "checkpoint" else "")
    )


def service(role, dbs):
    env = {**common, "SECURITY_ROLE": role}
    vol = ca_mount.copy()
    files = {}
    for db in dbs:
        filename = db + ".dsn"
        (OUT / filename).write_text(dsn(db))
        files[db + "_database_url"] = "/secrets/" + filename
        vol.append("./" + filename + ":/secrets/" + filename + ":ro")
    if role == "api":
        files.update(session_signing_key="/secrets/session.key", idp_token_key="/secrets/token.key")
        vol += ["./session.key:/secrets/session.key:ro", "./token.key:/secrets/token.key:ro"]
    env["SECRET_FILES"] = json.dumps(files)
    if role in ["api", "mcp"]:
        env.update(TLS_CERT_FILE="/tls/" + role + ".crt", TLS_KEY_FILE="/tls/" + role + ".key")
        vol += mounts(role + ".crt", role + ".key")
    if role == "api":
        vol += ["./service-private/current.pem:/run/service-private/current.pem:ro"]
    if role == "worker":
        vol += ["./service-private:/run/service-private:ro"]
    if role == "mcp":
        vol += ["./service-public:/run/service-public:ro"]
    return {
        "image": "opspilot-full/app:f01",
        "init": True,
        "environment": env,
        "volumes": vol,
        "cap_drop": ["ALL"],
        "security_opt": ["no-new-privileges:true"],
        "read_only": True,
        "tmpfs": ["/tmp"],
        "depends_on": {"postgres": {"condition": "service_healthy"}},
    }


services = {}
services["postgres"] = {
    "image": "opspilot-full/postgres:f01",
    "environment": {
        "POSTGRES_USER": "ops_migration",
        "POSTGRES_DB": "opspilot_full_test",
        "POSTGRES_PASSWORD": passwords["migration"],
        "WORKFLOW_DB_PASSWORD": passwords["workflow"],
        "DOMAIN_DB_PASSWORD": passwords["domain"],
        "CHECKPOINT_DB_PASSWORD": passwords["checkpoint"],
    },
    "volumes": [
        "pgdata:/var/lib/postgresql/data",
        "../../infra/postgres/init.sql:/docker-entrypoint-initdb.d/001-init.sql:ro",
        "../../infra/security/pg_hba.conf:/etc/security/pg_hba.conf:ro",
    ]
    + mounts("postgres.crt", "postgres.key"),
    "entrypoint": [
        "sh",
        "-ec",
        "cp /tls/postgres.key /tmp/server.key; chown postgres:postgres /tmp/server.key; chmod 600 /tmp/server.key; exec docker-entrypoint.sh postgres -c ssl=on -c ssl_cert_file=/tls/postgres.crt -c ssl_key_file=/tmp/server.key -c ssl_min_protocol_version=TLSv1.2 -c hba_file=/etc/security/pg_hba.conf",
    ],
    "healthcheck": {
        "test": ["CMD-SHELL", "pg_isready -U ops_migration -d opspilot_full_test"],
        "interval": "2s",
        "retries": 30,
    },
}
services["oidc"] = {
    "image": "opspilot-full/oidc:f03",
    "command": [
        "start",
        "--import-realm",
        "--http-enabled=false",
        "--cache=local",
        "--https-port=8543",
        "--https-certificate-file=/tls/idp.opspilot.localhost.crt",
        "--https-certificate-key-file=/tls/idp.opspilot.localhost.key",
        "--https-protocols=TLSv1.3,TLSv1.2",
    ],
    "environment": {
        "KC_HOSTNAME": "https://idp.opspilot.localhost:8543",
        "KC_BOOTSTRAP_ADMIN_USERNAME": "security-admin",
        "KC_BOOTSTRAP_ADMIN_PASSWORD": passwords["admin"],
    },
    "volumes": [
        "oidcdata:/opt/keycloak/data",
        "../../infra/identity/password-blacklists:/opt/keycloak/data/password-blacklists:ro",
        "./realm.json:/opt/keycloak/data/import/opspilot-realm.json:ro",
    ]
    + mounts("idp.opspilot.localhost.crt", "idp.opspilot.localhost.key"),
    "ports": ["127.0.0.1:8543:8543"],
    "networks": {"default": {"aliases": ["idp.opspilot.localhost"]}},
}
for role, dbs in [
    ("api", ["identity", "workflow", "checkpoint"]),
    ("worker", ["workflow", "checkpoint"]),
    ("mcp", ["domain"]),
    ("admin", ["migration"]),
]:
    services[role] = service(role, dbs)
services["api"]["healthcheck"] = {
    "test": [
        "CMD",
        "python",
        "-c",
        "import httpx,ssl; r=httpx.get('https://api:8000/health',verify=ssl.create_default_context(cafile='/tls/ca.crt'),timeout=10);r.raise_for_status()",
    ],
    "interval": "5s",
    "timeout": "12s",
    "retries": 30,
    "start_period": "20s",
}
services["worker"]["command"] = ["python", "-m", "opspilot.runtime.worker"]
services["mcp"]["command"] = ["python", "-m", "opspilot.mcp_server.main"]
services["admin"].update(profiles=["tools"], command=["alembic", "upgrade", "head"])
services["admin"]["environment"]["IDENTITY_DB_PASSWORD"] = passwords["identity"]
services["web"] = {
    "image": "opspilot-full/web:f01",
    "volumes": ["../../infra/security/nginx.conf:/etc/nginx/conf.d/default.conf:ro"]
    + mounts("ca.crt", "app.opspilot.localhost.crt", "app.opspilot.localhost.key"),
    "ports": ["127.0.0.1:8443:8443"],
    "depends_on": {"api": {"condition": "service_healthy"}},
    "networks": {"default": {"aliases": ["app.opspilot.localhost"]}},
}
services["probe"] = {
    "image": "opspilot-full/tests:f01",
    "profiles": ["tools"],
    "volumes": ["../../:/work:ro", "./:/lab:ro", "../../docs/security/hardening/evidence:/reports"]
    + services["api"]["volumes"],
    "working_dir": "/work",
    "environment": services["api"]["environment"],
    "command": ["python", "/work/scripts/security_local_probe.py"],
}
services["browser"] = {
    "image": "opspilot-full/e2e:f01",
    "profiles": ["tools"],
    "volumes": ["../../:/work:ro", "./:/lab:ro", "../../docs/security/hardening/evidence:/reports"],
    "environment": {"NODE_EXTRA_CA_CERTS": "/lab/ca.crt"},
    "command": ["node", "/work/scripts/security_local_browser.mjs"],
}
(OUT / "compose.json").write_text(
    json.dumps(
        {
            "name": "opspilot-full-security",
            "services": services,
            "volumes": {"pgdata": {}, "oidcdata": {}},
        },
        indent=2,
    )
)
print("Isolated TLS/MFA lab generated. Credentials remain ignored; CA not installed in OS.")

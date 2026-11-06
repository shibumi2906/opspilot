"""Compare current Full source with installed application/tests and served proxy image."""

import hashlib
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path


def hashes(root):
    return {
        p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(root.rglob("*.py"))
    }


def python_image(image, code):
    return json.loads(
        subprocess.check_output(
            [
                "docker",
                "run",
                "--rm",
                "--network",
                "none",
                "--memory",
                "192m",
                "--entrypoint",
                "python",
                image,
                "-c",
                code,
            ],
            text=True,
        )
    )


probe = (
    "import hashlib,json;from pathlib import Path;{root};"
    "print(json.dumps({{p.relative_to(root).as_posix():"
    "hashlib.sha256(p.read_bytes()).hexdigest() "
    "for p in sorted(root.rglob('*.py'))}}))"
)
app = python_image(
    "opspilot-full/app:f01",
    probe.format(root="import opspilot;root=Path(opspilot.__file__).parent"),
)
assert app == hashes(Path("src/opspilot")), "Installed app source mismatch"
tests = python_image("opspilot-full/tests:f01", probe.format(root="root=Path('/app/tests')"))
assert tests == hashes(Path("tests")), "Installed test source mismatch"
migrations = python_image(
    "opspilot-full/app:f01", probe.format(root="root=Path('/app/migrations')")
)
assert migrations == hashes(Path("migrations")), "Migration source mismatch"
nginx = subprocess.check_output(
    [
        "docker",
        "run",
        "--rm",
        "--network",
        "none",
        "--entrypoint",
        "sha256sum",
        "opspilot-full/web:f01",
        "/etc/nginx/conf.d/default.conf",
    ],
    text=True,
).split()[0]
assert nginx == hashlib.sha256(Path("web/nginx.conf").read_bytes()).hexdigest(), (
    "Served proxy source mismatch"
)
result = {
    "passed": True,
    "observed_at_utc": datetime.now(UTC).isoformat(),
    "base": "017b68bb34e85e95013076d570bd14b5519f842b",
    "installed_python_files": len(app),
    "test_python_files": len(tests),
    "migration_files": len(migrations),
    "nginx_source_matches": True,
    "app": app,
    "tests": tests,
    "migrations": migrations,
    "nginx_sha256": nginx,
}
Path("docs/full/evidence/f18/source-image-match.json").write_text(
    json.dumps(result, indent=2) + "\n"
)
print(
    json.dumps(
        {
            k: result[k]
            for k in (
                "passed",
                "installed_python_files",
                "test_python_files",
                "migration_files",
                "nginx_source_matches",
            )
        }
    )
)

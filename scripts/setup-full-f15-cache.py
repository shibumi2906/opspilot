"""Prepare only private ignored Full Redis credentials. Never rotate an existing secret."""

import argparse
import secrets
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--test", action="store_true", help="Use separate local test cache credentials")
args = parser.parse_args()
root = Path(".tools/cache-test" if args.test else ".tools/cache")
root.mkdir(parents=True, exist_ok=True)
for name in ("password", "signing-key"):
    p = root / name
    if not p.exists():
        p.write_text(secrets.token_hex(32) + "\n", encoding="ascii", newline="\n")
password = (root / "password").read_text().strip()
for name in ("password", "signing-key"):
    p = root / name
    p.write_text(p.read_text().strip() + "\n", encoding="ascii", newline="\n")
assert len(password) == 64 and all(c in "0123456789abcdef" for c in password)
(root / "redis.acl").write_text(
    "user default off\nuser cache on >"
    + password
    + " ~opspilot-full:* +get +set +incr +expire +eval +ping\n",
    encoding="ascii",
    newline="\n",
)
print("Ignored Full Redis credentials prepared; existing password/signing key preserved")

"""Bound every RSA parameter before Go's cubic validation (CVE-2026-116587).

v3 is unsupported upstream; retain original version/module metadata and explicit proof.
v4 uses the published 4.1.6 fix instead. No scanner suppression or renamed dependency.
"""

import hashlib
import json
import sys
from pathlib import Path

root = Path(sys.argv[1])
path = root / "jwk.go"
original = path.read_text()
patched = original
for name, return_type in (("rsaPrivateKey", "*rsa.PrivateKey"), ("rsaPublicKey", "*rsa.PublicKey")):
    marker = f"func (key rawJSONWebKey) {name}() ({return_type}, error) {{"
    assert patched.count(marker) == 1, "Unexpected upstream source; review patch"
    guard = '''
    // OpsPilot F17 vendor backport: validate bounds BEFORE any RSA arithmetic.
    // Same 4096-bit project maximum as upstream v4.1.6; no runtime escape hatch.
    for _, part := range []*byteBuffer{key.N, key.D, key.P, key.Q, key.Dp, key.Dq, key.Qi} {
        if part != nil && len(part.bytes()) > 512 {
            return nil, errors.New("go-jose/go-jose: RSA parameters exceed 4096 bits")
        }
    }
    if key.E != nil && len(key.E.bytes()) > 4 {
        return nil, errors.New("go-jose/go-jose: RSA exponent exceeds 32 bits")
    }
'''
    patched = patched.replace(marker, marker + guard, 1)
path.write_text(patched)
(root / "f17-patch-proof.json").write_text(json.dumps({
    "advisory": "CVE-2026-116587", "module": "github.com/go-jose/go-jose/v3@v3.0.5",
    "upstream_fixed_v4_commit": "a0111f82742fa92bceec9ede40845e73319e6230",
    "original_jwk_sha256": hashlib.sha256(original.encode()).hexdigest(),
    "patched_jwk_sha256": hashlib.sha256(patched.encode()).hexdigest(),
    "patch_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    "control": "all RSA operands bounded before Validate; N/D/P/Q/CRT<=4096 bits, E<=32 bits",
    "metadata_preserved": True,
}, indent=2) + "\n")

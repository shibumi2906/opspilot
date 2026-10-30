"""Verify narrowly scoped component applicability without altering the raw scan."""

import argparse
import hashlib
import json
import posixpath
import struct
import tarfile
from datetime import UTC, datetime
from pathlib import Path

EXPECTED_HASH = "632fd43a9d8d6f3496833b7e62e7840f397163373dddf8b8eb0b2b7f36593117"
LIBRARY = "usr/lib/x86_64-linux-gnu/libuuid.so.1.3.0"
ADVISORIES = {
    "CVE-2026-76642": "GHSA-m25x-3hj9-m26f",
    "CVE-2026-78408": "GHSA-55fx-f4gg-cfhj",
    "CVE-2026-78409": "GHSA-8f2p-47x3-43mv",
    "CVE-2026-78410": "GHSA-rh77-686x-2f2m",
}


def require(condition, message):
    if not condition:
        raise SystemExit(message)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def exports(data):
    require(data[:6] == b"\x7fELF\x02\x01", "Expected ELF64 little endian")
    header = struct.unpack_from("<16sHHIQQQIHHHHHH", data)
    offset, size, count = header[6], header[11], header[12]
    sections = [struct.unpack_from("<IIQQQQIIQQ", data, offset + i * size) for i in range(count)]
    names = []
    for section in sections:
        if section[1] != 11:  # SHT_DYNSYM
            continue
        strings_section = sections[section[6]]
        strings = data[strings_section[4] : strings_section[4] + strings_section[5]]
        for offset in range(section[4], section[4] + section[5], section[9]):
            name, _, _, defined, _, _ = struct.unpack_from("<IBBHQQ", data, offset)
            if defined and name:
                names.append(strings[name : strings.index(b"\0", name)].decode("ascii"))
    require(
        names and all(n.lower().startswith(("uuid", "__uuid")) for n in names),
        "Unexpected library exports",
    )
    return sorted(names)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--scan", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    raw = args.scan.read_bytes()
    report = json.loads(raw.decode("utf-8-sig"))
    findings = [
        v
        for r in report["Results"]
        for v in r.get("Vulnerabilities", [])
        if v["Severity"] in ("HIGH", "CRITICAL")
    ]
    require(
        len(findings) == 4 and {v["VulnerabilityID"] for v in findings} == set(ADVISORIES),
        "Unexpected HIGH/CRITICAL finding set; manual investigation required",
    )
    require(
        all(
            v["PkgName"] == "libuuid1" and v["InstalledVersion"] == "2.41.5-0+deb13u1"
            for v in findings
        ),
        "Unexpected affected package/version",
    )
    inventory = {}
    payload = {}
    with tarfile.open(args.archive) as archive:
        manifests = json.load(archive.extractfile("manifest.json"))
        require(len(manifests) == 1, "Expected exactly one image")
        manifest = manifests[0]
        config_raw = archive.extractfile(manifest["Config"]).read()
        image_id = "sha256:" + digest(config_raw)
        require(image_id == report["Metadata"]["ImageID"], "Scan/archive image mismatch")
        config = json.loads(config_raw)
        layers = config["rootfs"]["diff_ids"]
        require(len(layers) == len(manifest["Layers"]), "Layer count mismatch")
        for member, expected in zip(manifest["Layers"], layers, strict=True):
            stream = archive.extractfile(member)
            hasher = hashlib.sha256()
            while chunk := stream.read(1024 * 1024):
                hasher.update(chunk)
            require("sha256:" + hasher.hexdigest() == expected, "Layer digest mismatch")
            with tarfile.open(fileobj=archive.extractfile(member)) as layer:
                members = list(layer)
                # OCI whiteouts apply to lower layers, before entries in this layer.
                for entry in members:
                    name = entry.name.removeprefix("./")
                    base, leaf = posixpath.split(name)
                    if leaf.startswith(".wh."):
                        target = base if leaf == ".wh..wh..opq" else posixpath.join(base, leaf[4:])
                        for prior in list(inventory):
                            if prior == target or prior.startswith(target + "/"):
                                del inventory[prior]
                                payload.pop(prior, None)
                for entry in members:
                    name = entry.name.removeprefix("./")
                    require(
                        not name.startswith("/") and ".." not in name.split("/"),
                        "Unsafe archive path",
                    )
                    if posixpath.basename(name).startswith(".wh."):
                        continue
                    inventory[name] = (
                        entry.linkname
                        if entry.issym() or entry.islnk()
                        else "file"
                        if entry.isfile()
                        else "directory"
                    )
                    if name in (LIBRARY, "var/lib/dpkg/status.d/libuuid1"):
                        require(entry.isfile(), "Unexpected library/package entry type")
                        payload[name] = layer.extractfile(entry).read()
    prohibited = [
        n
        for n in inventory
        if "libmount" in n
        or posixpath.basename(n) == "nsenter"
        or (posixpath.basename(n) in ("mount", "umount") and not n.startswith("busybox/"))
    ]
    require(not prohibited, "Affected util-linux component present: " + repr(prohibited))
    require(
        digest(payload[LIBRARY]) == EXPECTED_HASH, "Unreviewed libuuid bytes; re-review required"
    )
    symbols = exports(payload[LIBRARY])
    package = payload["var/lib/dpkg/status.d/libuuid1"].decode()
    require(
        "Version: 2.41.5-0+deb13u1\n" in package and "Source: util-linux\n" in package,
        "Package identity mismatch",
    )
    require(inventory.get("busybox/mount") == "/busybox/busybox", "Unexpected mount implementation")
    result = {
        "verified_at": datetime.now(UTC).isoformat(),
        "image_id": image_id,
        "raw_scan_sha256": digest(raw),
        "verified_layer_count": len(layers),
        "raw_high_critical": len(findings),
        "applicable_high_critical": 0,
        "disposition": "vulnerable_code_not_present",
        "scope": (
            "Exact image and exact four source-package-attributed findings only; "
            "no risk acceptance, scanner ignore or ASVS requirement N/A"
        ),
        "library": {"path": LIBRARY, "sha256": EXPECTED_HASH, "defined_dynamic_symbols": symbols},
        "absent_components": [
            "util-linux libmount shared library",
            "util-linux mount/umount",
            "util-linux nsenter",
        ],
        "other_mount_implementation": (
            "Upstream static BusyBox applet retained; does not contain util-linux libmount code"
        ),
        "reason": (
            "Upstream advisories identify libmount mount hooks/detached trees or "
            "nsenter cgroup FD code. Exact libuuid ELF exports only UUID APIs and "
            "version symbols; affected components absent from verified final filesystem."
        ),
        "findings": [
            {
                "id": key,
                "source": "https://github.com/util-linux/util-linux/security/advisories/" + value,
            }
            for key, value in ADVISORIES.items()
        ],
    }
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print("Verified raw HIGH/CRITICAL=4; applicable=0 for exact image " + image_id)


if __name__ == "__main__":
    main()

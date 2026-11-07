"""Explicitly authorized disposable F19 target; secrets/artifacts remain under .tools.

No implicit deployment: prepare, provision and destroy are separate commands.
Uses AWS CLI login credentials; never exports credentials or changes IAM.
"""

import argparse
import hashlib
import ipaddress
import json
import subprocess
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
PRIVATE = ROOT / ".tools/f19-aws-staging"
LEDGER = PRIVATE / "resources.json"
REGION = "il-central-1"


def run(args):
    result = subprocess.run(args, cwd=ROOT, capture_output=True, text=True)
    if result.returncode:
        (PRIVATE / "last-command-error.txt").write_text(result.stderr, encoding="utf-8")
        # Do not echo provider responses, user-data or credential-bearing arguments.
        raise RuntimeError(f"Command failed: {args[0]} {args[1]} (exit {result.returncode})")
    return result.stdout


def aws(profile, service, operation, **values):
    args = [
        "aws",
        service,
        operation,
        "--profile",
        profile,
        "--region",
        REGION,
        "--output",
        "json",
        "--no-cli-pager",
    ]
    for key, value in values.items():
        if isinstance(value, bool):
            args.append("--" + ("" if value else "no-") + key.replace("_", "-"))
            continue
        args += [
            "--" + key.replace("_", "-"),
            value if isinstance(value, str) else json.dumps(value),
        ]
    output = run(args)
    return json.loads(output) if output.strip() else {}


def save(state):
    temp = LEDGER.with_suffix(".tmp")
    temp.write_text(json.dumps(state, indent=2), encoding="utf-8")
    temp.replace(LEDGER)


def prepare():
    PRIVATE.mkdir(parents=True, exist_ok=True)
    if LEDGER.exists():
        raise RuntimeError("Ledger exists; inspect/reuse explicitly, never overwrite")
    identity = str(uuid4())
    state = {
        "run": identity,
        "region": REGION,
        "approved_usd": 5,
        "approved_hours": 24,
        "created_at": datetime.now(UTC).isoformat(),
        "phase": "prepared",
        "resources": {},
    }
    binary = PRIVATE / "prometheus"
    if not binary.is_file():
        raise RuntimeError("Export accepted F19 amd64 Prometheus binary first")
    state["binary_sha256"] = hashlib.sha256(binary.read_bytes()).hexdigest()
    key = PRIVATE / "ssh-key"
    if key.exists():
        raise RuntimeError("Existing SSH key must not be overwritten")
    run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(key)])
    save(state)
    print("Prepared local staging ledger and SSH key; no AWS mutation")


def provision(profile):
    state = json.loads(LEDGER.read_text())
    if state["phase"] != "prepared" or state["resources"]:
        raise RuntimeError("Partial/existing deployment: inspect ledger; do not duplicate")
    identity = aws(profile, "sts", "get-caller-identity")
    if identity["Account"] != "423741523738":
        raise RuntimeError("Unexpected AWS account")
    # Network-only prerequisites and AMI metadata precede any mutation.
    with urllib.request.urlopen("https://checkip.amazonaws.com", timeout=10) as response:
        operator = str(ipaddress.IPv4Address(response.read(128).decode().strip()))
    state["operator_cidr"] = operator + "/32"
    ami = aws(
        profile,
        "ssm",
        "get-parameter",
        name="/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64",
    )["Parameter"]["Value"]
    image = aws(profile, "ec2", "describe-images", image_ids=ami, owners="amazon")["Images"][0]
    if image["Architecture"] != "x86_64" or image.get("ImageOwnerAlias") != "amazon":
        raise RuntimeError("AMI must be Amazon-owned x86_64")
    state["ami"] = ami
    tags = [{"Key": "Project", "Value": "OpsPilotF19"}, {"Key": "F19Run", "Value": state["run"]}]

    def tagged(kind):
        return [{"ResourceType": kind, "Tags": tags}]

    def record(key, value):
        state["resources"][key] = value
        save(state)
        return value

    state["phase"] = "provisioning"
    save(state)
    # Record every returned ID immediately. Failures leave the ledger for cleanup.
    vpc = record(
        "vpc",
        aws(
            profile,
            "ec2",
            "create-vpc",
            cidr_block="10.197.0.0/24",
            tag_specifications=tagged("vpc"),
        )["Vpc"]["VpcId"],
    )
    subnet = record(
        "subnet",
        aws(
            profile,
            "ec2",
            "create-subnet",
            vpc_id=vpc,
            cidr_block="10.197.0.0/26",
            tag_specifications=tagged("subnet"),
        )["Subnet"]["SubnetId"],
    )
    gateway = record(
        "gateway",
        aws(
            profile, "ec2", "create-internet-gateway", tag_specifications=tagged("internet-gateway")
        )["InternetGateway"]["InternetGatewayId"],
    )
    aws(profile, "ec2", "attach-internet-gateway", internet_gateway_id=gateway, vpc_id=vpc)
    route = record(
        "route",
        aws(
            profile,
            "ec2",
            "create-route-table",
            vpc_id=vpc,
            tag_specifications=tagged("route-table"),
        )["RouteTable"]["RouteTableId"],
    )
    record(
        "association",
        aws(profile, "ec2", "associate-route-table", route_table_id=route, subnet_id=subnet)[
            "AssociationId"
        ],
    )
    aws(
        profile,
        "ec2",
        "create-route",
        route_table_id=route,
        destination_cidr_block="0.0.0.0/0",
        gateway_id=gateway,
    )
    group = record(
        "group",
        aws(
            profile,
            "ec2",
            "create-security-group",
            vpc_id=vpc,
            group_name="opspilot-f19-" + state["run"],
            description="Disposable F19 operator-only staging",
            tag_specifications=tagged("security-group"),
        )["GroupId"],
    )
    aws(
        profile,
        "ec2",
        "authorize-security-group-ingress",
        group_id=group,
        ip_permissions=[
            {
                "IpProtocol": "tcp",
                "FromPort": port,
                "ToPort": port,
                "IpRanges": [{"CidrIp": state["operator_cidr"]}],
            }
            for port in (22, 8443)
        ],
    )
    keyname = "opspilot-f19-" + state["run"]
    aws(
        profile,
        "ec2",
        "import-key-pair",
        key_name=keyname,
        public_key_material="fileb://" + str(PRIVATE / "ssh-key.pub"),
        tag_specifications=tagged("key-pair"),
    )
    record("key", keyname)
    launch(profile)


def launch(profile):
    state = json.loads(LEDGER.read_text())
    required = {"vpc", "subnet", "gateway", "route", "association", "group", "key"}
    if state["phase"] != "provisioning" or set(state["resources"]) != required:
        raise RuntimeError("Launch requires exact recorded infrastructure and no existing instance")
    # Check tag-filtered inventory before retrying an unknown launch outcome.
    existing = aws(
        profile,
        "ec2",
        "describe-instances",
        filters=[
            {"Name": "tag:F19Run", "Values": [state["run"]]},
            {
                "Name": "instance-state-name",
                "Values": ["pending", "running", "stopping", "stopped"],
            },
        ],
    )["Reservations"]
    if existing:
        raise RuntimeError("Instance already exists; reconcile ledger instead of relaunching")
    image = aws(profile, "ec2", "describe-images", image_ids=state["ami"], owners="amazon")[
        "Images"
    ][0]
    tags = [{"Key": "Project", "Value": "OpsPilotF19"}, {"Key": "F19Run", "Value": state["run"]}]

    def tagged(kind):
        return [{"ResourceType": kind, "Tags": tags}]

    # Arm OS termination before package/install work. Server also gets an absolute
    # deadline timer during configuration; manual teardown remains mandatory.
    bootstrap = """#!/bin/bash
set -eu
shutdown -P +1380
id opspilot >/dev/null 2>&1 || useradd --system --no-create-home --shell /sbin/nologin opspilot
mkdir -p /opt/opspilot-f19 /var/lib/opspilot-f19
chown opspilot:opspilot /var/lib/opspilot-f19
"""
    root_device = image["RootDeviceName"]
    result = aws(
        profile,
        "ec2",
        "run-instances",
        image_id=state["ami"],
        instance_type="t3.small",
        count="1",
        client_token=state["run"],
        key_name=state["resources"]["key"],
        network_interfaces=[
            {
                "DeviceIndex": 0,
                "SubnetId": state["resources"]["subnet"],
                "Groups": [state["resources"]["group"]],
                "AssociatePublicIpAddress": True,
                "DeleteOnTermination": True,
            }
        ],
        block_device_mappings=[
            {
                "DeviceName": root_device,
                "Ebs": {
                    "VolumeSize": 20,
                    "VolumeType": "gp3",
                    "Encrypted": True,
                    "DeleteOnTermination": True,
                },
            }
        ],
        credit_specification={"CpuCredits": "standard"},
        metadata_options={
            "HttpTokens": "required",
            "HttpEndpoint": "enabled",
            "HttpPutResponseHopLimit": 1,
        },
        instance_initiated_shutdown_behavior="terminate",
        user_data=bootstrap,
        tag_specifications=tagged("instance") + tagged("volume"),
    )
    state["resources"]["instance"] = result["Instances"][0]["InstanceId"]
    state["phase"] = "launched"
    save(state)
    print("One authorized instance launched; ledger saved. Configure and verify timer immediately.")


def destroy(profile):
    state = json.loads(LEDGER.read_text())
    resources = state["resources"]
    if state["region"] != REGION or not resources:
        raise RuntimeError("No recorded resources")
    # Verify ownership of every still-recorded taggable resource BEFORE deleting.
    ids = [
        resources[k]
        for k in ("instance", "group", "route", "gateway", "subnet", "vpc")
        if k in resources
    ]
    for resource in ids:
        tags = aws(
            profile, "ec2", "describe-tags", filters=[{"Name": "resource-id", "Values": [resource]}]
        )["Tags"]
        if not any(t["Key"] == "F19Run" and t["Value"] == state["run"] for t in tags):
            raise RuntimeError("Ownership tag mismatch; stop for review")

    def remove(key, operation, **kwargs):
        if key in resources:
            aws(profile, "ec2", operation, **kwargs)
            del resources[key]
            save(state)

    if "instance" in resources:
        instance = resources["instance"]
        aws(profile, "ec2", "terminate-instances", instance_ids=instance)
        run(
            [
                "aws",
                "ec2",
                "wait",
                "instance-terminated",
                "--instance-ids",
                instance,
                "--profile",
                profile,
                "--region",
                REGION,
            ]
        )
        del resources["instance"]
        save(state)
    remove("key", "delete-key-pair", key_name=resources.get("key", ""))
    remove("group", "delete-security-group", group_id=resources.get("group", ""))
    remove(
        "association", "disassociate-route-table", association_id=resources.get("association", "")
    )
    remove("route", "delete-route-table", route_table_id=resources.get("route", ""))
    if "gateway" in resources:
        aws(
            profile,
            "ec2",
            "detach-internet-gateway",
            internet_gateway_id=resources["gateway"],
            vpc_id=resources["vpc"],
        )
    remove("gateway", "delete-internet-gateway", internet_gateway_id=resources.get("gateway", ""))
    remove("subnet", "delete-subnet", subnet_id=resources.get("subnet", ""))
    remove("vpc", "delete-vpc", vpc_id=resources.get("vpc", ""))
    state["phase"] = "deleted"
    save(state)
    print("Recorded resources removed; verify volumes/ENIs and delayed billing separately")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["prepare", "provision", "launch", "destroy"])
    parser.add_argument("--profile", default="opspilot-admin-setup")
    args = parser.parse_args()
    if args.action == "prepare":
        prepare()
    elif args.action == "provision":
        provision(args.profile)
    elif args.action == "launch":
        launch(args.profile)
    else:
        destroy(args.profile)

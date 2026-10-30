"""Prepare ignored Full telemetry material; never rotate existing files."""

import argparse
from pathlib import Path

from opspilot.observability.provision import prepare

p = argparse.ArgumentParser(description=__doc__)
p.add_argument("--test", action="store_true")
p.add_argument("--directory", type=Path)
args = p.parse_args()
root = args.directory or Path(".tools/observability-test" if args.test else ".tools/observability")
prepare(root)
print("Private telemetry credentials ready; existing identities and integrity key preserved")

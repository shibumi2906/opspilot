"""F21-only manager: new identities/volumes, only its own lab network; preserve F17/dev."""

import argparse
import importlib.util
import re
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--project", default="opspilot-full-test-f21-r1")
args = parser.parse_args()

if not re.fullmatch(r"opspilot-full-test-f21-[a-z0-9-]+", args.project):
    parser.error("F21 isolated project required")
path = Path(__file__).with_name("setup-full-f17-manager.py")
spec = importlib.util.spec_from_file_location("f21_manager_provisioner", path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
module.PRIVATE = Path.cwd() / ".tools/f21" / args.project / "manager"
module.RECOVERY = Path.cwd() / ".tools/f21" / args.project / "recovery"
module.PROJECT = args.project + "-manager"
module.PORT = 18226
module.APPLICATION_NETWORKS = ()
module.EXTERNAL_NETWORK = args.project + "_default"
module.bootstrap()

"""Create only dedicated Full telemetry volume directories, never replace journal/seals."""

import os
import sys
from pathlib import Path

for name in ("/var/lib/opspilot-observability", "/var/lib/opspilot-seals"):
    path = Path(name)
    path.mkdir(parents=True, exist_ok=True)
    if sys.platform != "win32":
        os.chown(path, 10001, 10001)
    else:
        raise RuntimeError("Initialize telemetry volumes only in the Linux container")
    os.chmod(path, 0o700)

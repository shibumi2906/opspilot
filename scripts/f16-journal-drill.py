"""Only called with test collector mounts by the guarded F16 drill runner."""
from pathlib import Path
import hashlib
import json
import shutil
import sqlite3
import sys

mode = sys.argv[1]
data = Path("/var/lib/opspilot-observability/journal.db")
seal = Path("/var/lib/opspilot-seals/head.json")
backup = Path("/backup")
if mode in ("original", "corrupt"):
    folder = backup / mode
    folder.mkdir()
    for source in (data, seal):
        shutil.copy2(source, folder / source.name)
    (folder / "hashes.json").write_text(json.dumps({
        p.name: hashlib.sha256(p.read_bytes()).hexdigest()
        for p in folder.iterdir() if p.is_file()
    }))
elif mode == "tamper":
    connection = sqlite3.connect(data)
    assert connection.execute("SELECT count(*) FROM events").fetchone()[0] > 0
    connection.execute("UPDATE events SET body='{}' WHERE seq=(SELECT min(seq)+(max(seq)-min(seq))/2 FROM events)")
    connection.commit()
    connection.close()
elif mode == "restore":
    folder = backup / "original"
    hashes = json.loads((folder / "hashes.json").read_text())
    for target in (data, seal):
        source = folder / target.name
        assert hashlib.sha256(source.read_bytes()).hexdigest() == hashes[source.name]
        shutil.copyfile(source, target)
        target.chmod(0o600)
    print("Verified original journal/seal restored; corrupt copy preserved privately")
else:
    raise ValueError("Unknown drill mode")

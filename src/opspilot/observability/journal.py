"""A bounded metadata-only journal, sealed separately from its database."""

import hashlib
import hmac
import json
import os
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any


class IntegrityError(RuntimeError):
    pass


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


class Journal:
    def __init__(
        self,
        directory: Path,
        seal_directory: Path,
        key: bytes,
        *,
        limit: int = 10000,
        retention: int = 86400,
    ) -> None:
        if not 32 <= len(key) <= 128 or not 32 <= limit <= 100000 or not 60 <= retention <= 604800:
            raise ValueError("Invalid journal policy")
        self.directory = directory
        self.seals = seal_directory
        self.key = key
        self.limit = limit
        self.retention = retention
        self.lock = threading.RLock()
        self.failed = False
        directory.mkdir(parents=True, exist_ok=True)
        seal_directory.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(directory / "journal.db", check_same_thread=False, timeout=1)
        os.chmod(directory / "journal.db", 0o600)
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.execute("PRAGMA max_page_count=8192")
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS events(seq INTEGER PRIMARY KEY,stamp REAL NOT NULL,"
            "body TEXT NOT NULL,prev TEXT NOT NULL,mac TEXT NOT NULL)"
        )
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS state(id INTEGER PRIMARY KEY CHECK(id=1),"
            "body TEXT NOT NULL)"
        )
        if not self.db.execute("SELECT 1 FROM state").fetchone():
            if (seal_directory / "head.json").exists():
                raise IntegrityError("JOURNAL_MISSING")
            state = {
                "base_seq": 0,
                "base_mac": "0" * 64,
                "seq": 0,
                "mac": "0" * 64,
                "stamp": 0.0,
                "pruned": 0,
            }
            self.db.execute("INSERT INTO state VALUES(1,?)", (canonical(state).decode(),))
            self.db.commit()
            self._seal(state)
        self.verify()

    def _mac(self, value: Any) -> str:
        return hmac.new(self.key, canonical(value), hashlib.sha256).hexdigest()

    def _seal(self, state: dict[str, Any], pending: dict[str, Any] | None = None) -> None:
        value = {"state": state, "pending": pending}
        path = self.seals / "head.tmp"
        with path.open("wb") as stream:
            stream.write(canonical({"value": value, "mac": self._mac(value)}))
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(path, 0o600)
        os.replace(path, self.seals / "head.json")

    def state(self) -> dict[str, Any]:
        return dict(json.loads(self.db.execute("SELECT body FROM state WHERE id=1").fetchone()[0]))

    def verify(self) -> dict[str, Any]:
        with self.lock:
            try:
                sealed = json.loads((self.seals / "head.json").read_bytes())
                if not hmac.compare_digest(sealed["mac"], self._mac(sealed["value"])):
                    raise IntegrityError("SEAL_INVALID")
                state = self.state()
                allowed = sealed["value"]
                if allowed["pending"] is not None and state == allowed["pending"]:
                    self._seal(state)
                elif state != allowed["state"] or allowed["pending"] is not None:
                    raise IntegrityError("JOURNAL_HEAD_MISMATCH")
                seq = state["base_seq"]
                previous = state["base_mac"]
                for n, stamp, body, prior, mac in self.db.execute(
                    "SELECT seq,stamp,body,prev,mac FROM events ORDER BY seq"
                ):
                    if (
                        n != seq + 1
                        or prior != previous
                        or not hmac.compare_digest(mac, self._mac([n, stamp, body, prior]))
                    ):
                        raise IntegrityError("JOURNAL_CHAIN_INVALID")
                    seq = n
                    previous = mac
                if seq != state["seq"] or previous != state["mac"]:
                    raise IntegrityError("JOURNAL_TRUNCATED")
                if self.failed:
                    raise IntegrityError("JOURNAL_QUARANTINED")
                return state
            except (
                ValueError,
                KeyError,
                TypeError,
                sqlite3.DatabaseError,
                OSError,
                IntegrityError,
            ) as exc:
                self.failed = True
                raise IntegrityError("JOURNAL_INTEGRITY_FAILED") from exc

    def append(self, records: list[dict[str, Any]]) -> None:
        with self.lock:
            self.db.execute("BEGIN IMMEDIATE")
            try:
                state = self.verify()
                old = dict(state)
                now = time.time()
                if now + 5 < state["stamp"]:
                    self.failed = True
                    raise IntegrityError("CLOCK_REGRESSION")
                for record in records[:128]:
                    body = canonical(record).decode()
                    if len(body) > 8192:
                        continue
                    state["seq"] += 1
                    mac = self._mac([state["seq"], now, body, state["mac"]])
                    self.db.execute(
                        "INSERT INTO events VALUES(?,?,?,?,?)",
                        (state["seq"], now, body, state["mac"], mac),
                    )
                    state["mac"] = mac
                remove = self.db.execute(
                    "SELECT seq,mac FROM events WHERE stamp<? OR seq<=? ORDER BY seq DESC LIMIT 1",
                    (now - self.retention, state["seq"] - self.limit),
                ).fetchone()
                if remove:
                    n, mac = remove
                    deleted = self.db.execute(
                        "SELECT count(*) FROM events WHERE seq<=?", (n,)
                    ).fetchone()[0]
                    self.db.execute("DELETE FROM events WHERE seq<=?", (n,))
                    state.update(base_seq=n, base_mac=mac, pruned=state["pruned"] + deleted)
                state["stamp"] = now
                self.db.execute("UPDATE state SET body=? WHERE id=1", (canonical(state).decode(),))
                self._seal(old, state)
                self.db.commit()
                self._seal(state)
            except BaseException:
                self.db.rollback()
                raise

    def read(
        self, tenant: str, run: str | None = None, limit: int = 100, actor: str | None = None
    ) -> dict[str, Any]:
        with self.lock:
            self.db.execute("BEGIN")
            try:
                return self._read_snapshot(tenant, run, limit, actor)
            finally:
                self.db.rollback()

    def _read_snapshot(
        self, tenant: str, run: str | None, limit: int, actor: str | None
    ) -> dict[str, Any]:
        with self.lock:
            state = self.verify()
            items = []
            # Bounded retained window; raw payloads never enter this journal.
            retained = [
                (n, stamp, json.loads(body))
                for n, stamp, body in self.db.execute(
                    "SELECT seq,stamp,body FROM events ORDER BY seq DESC LIMIT 10000"
                )
            ]
            associated = {
                row.get("trace_id")
                for _, _, row in retained
                if row.get("attributes", {}).get("tenant_id") == tenant
                and row.get("attributes", {}).get("run_id") == run
            }
            for n, stamp, row in retained:
                attrs = row.get("attributes", {})
                if actor is not None and attrs.get("actor_id") != actor:
                    continue
                own_run = run is None or attrs.get("run_id") == run
                related = not attrs.get("run_id") and row.get("trace_id") in associated
                if attrs.get("tenant_id") == tenant and (own_run or related):
                    items.append({"sequence": n, "received_at": stamp, **row})

            # Keep the bounded view useful under SQL/SSE HTTP span volume.
            # Storage retains every admitted record; only presentation is prioritized.
            quiet = {"db.operation", "http.api", "http.mcp.server"}
            relevant = [r for r in items if r.get("name") not in quiet]
            detail = [r for r in items if r.get("name") in quiet]
            selected = (relevant + detail)[:limit]
            selected.sort(key=lambda r: r["sequence"], reverse=True)
            return {
                "events": selected,
                "selection": (
                    "latest workflow/security records first; DB/HTTP detail fills remaining slots"
                ),
                "matching_retained_records": len(items),
                "retention_pruned": state["pruned"],
                "integrity": "verified",
                "received_at": time.time(),
                "retention_seconds": self.retention,
            }

    def close(self) -> None:
        self.db.close()

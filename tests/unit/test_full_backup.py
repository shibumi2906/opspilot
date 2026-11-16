"""Retention boundaries and authenticated catalog tampering must preserve recovery files."""

import hashlib
import json
import runpy
from datetime import UTC, datetime, timedelta

import pytest
from cryptography.fernet import Fernet

MODULE = runpy.run_path("scripts/full_backup.py")
plan = MODULE["retention_plan"]
Store = MODULE["Store"]


def test_daily_and_weekly_recovery_points_survive_multiple_backups_per_day():
    now = datetime(2026, 11, 16, 18, tzinfo=UTC)
    rows = [
        {
            "id": f"{day}-{hour}",
            "created_at_utc": (now - timedelta(days=day, hours=hour)).isoformat(),
            "state": "verified",
            "hold": False,
        }
        for day in range(42)
        for hour in (0, 3)
    ]
    result = plan(rows, now)
    assert all(f"{day}-0" in result["keep"] for day in range(7))
    latest_by_week = {}
    for row in rows:
        week = datetime.fromisoformat(row["created_at_utc"]).isocalendar()[:2]
        latest_by_week.setdefault(week, row["id"])
    assert set(list(latest_by_week.values())[:4]) <= set(result["keep"])
    assert "0-3" in result["remove"]
    assert set(result["keep"]).isdisjoint(result["remove"])
    assert len(result["keep"]) + len(result["remove"]) == len(rows)


def test_unknown_or_unverified_backup_never_enters_prune_plan():
    now = datetime(2026, 11, 16, tzinfo=UTC)
    rows = [
        {
            "id": str(n),
            "created_at_utc": (now - timedelta(days=n)).isoformat(),
            "state": "verified",
            "hold": False,
        }
        for n in range(60)
    ]
    rows[59]["hold"] = True
    rows[58]["state"] = "incomplete"
    result = plan(rows, now)
    assert {"58", "59"} <= set(result["keep"])
    rows[0]["created_at_utc"] = (now + timedelta(hours=1)).isoformat()
    with pytest.raises(ValueError, match="clock"):
        plan(rows, now)


def test_catalog_date_tampering_cannot_delete_any_archive(tmp_path, monkeypatch):
    monkeypatch.setitem(Store.__init__.__globals__, "ROOT", tmp_path)
    root = tmp_path / ".tools"
    root.mkdir()
    config = root / "backup.json"
    config.write_text(
        json.dumps(
            {
                "project": "opspilot-full-test-f23-unit",
                "archive_root": str(root / "archives"),
                "key_root": str(root / "keys"),
            }
        )
    )
    with Store(config) as store:
        metadata = {
            "id": "20261116T000000Z-abcdef123456",
            "created_at_utc": "2026-11-16T00:00:00+00:00",
            "state": "verified",
            "hold": False,
            "project": store.project,
        }
        archive, keyfile = store.paths(metadata["id"])
        key = Fernet.generate_key()
        raw = Fernet(key).encrypt(json.dumps({"metadata": metadata}).encode())
        keyfile.write_bytes(key)
        archive.write_bytes(raw)
        row = {**metadata, "encrypted_sha256": hashlib.sha256(raw).hexdigest()}
        store.save([{**row, "created_at_utc": "2020-01-01T00:00:00+00:00"}])
        with pytest.raises(ValueError, match="authenticated"):
            store.prune(apply=True)
        assert archive.read_bytes() == raw
        assert keyfile.read_bytes() == key


def test_interrupted_operation_resumes_exact_recorded_services_before_new_backup(
    tmp_path, monkeypatch
):
    store = object.__new__(Store)
    store.project = "opspilot-full-test-f23-unit"
    store.journal = tmp_path / "operation.json"
    running = ["postgres", "redis", "api"]  # Deliberately stopped worker must stay stopped.
    store.record_services(running, ["manager"])
    resumed = []
    monkeypatch.setattr(store, "validate_profile", lambda: None)
    monkeypatch.setattr(store, "resume_services", lambda a, m: resumed.append((a, m)))
    assert store.recover_interrupted() is True
    assert resumed == [(running, ["manager"])]
    assert not store.journal.exists()
    assert store.recover_interrupted() is False


def test_failed_resume_keeps_journal_for_next_attempt(tmp_path, monkeypatch):
    store = object.__new__(Store)
    store.project = "opspilot-full-test-f23-unit"
    store.journal = tmp_path / "operation.json"
    store.record_services(["postgres", "api"], ["manager"])
    monkeypatch.setattr(store, "validate_profile", lambda: None)

    def unavailable(*_):
        raise RuntimeError("manager unavailable")

    monkeypatch.setattr(store, "resume_services", unavailable)
    with pytest.raises(RuntimeError, match="unavailable"):
        store.recover_interrupted()
    assert store.journal.exists()


def test_unexpected_journal_service_never_starts_a_tool(monkeypatch):
    store = object.__new__(Store)

    def forbidden(*_, **__):
        pytest.fail("Unexpected service must be rejected before any Docker operation")

    monkeypatch.setitem(Store.resume_services.__globals__, "compose", forbidden)
    with pytest.raises(ValueError, match="Unexpected service"):
        store.resume_services(["postgres", "operator"], ["manager"])


def test_lock_contention_cannot_overlap_capture_and_releases_on_exit(tmp_path, monkeypatch):
    monkeypatch.setitem(Store.__init__.__globals__, "ROOT", tmp_path)
    root = tmp_path / ".tools"
    root.mkdir()
    config = root / "config.json"
    config.write_text(
        json.dumps(
            {
                "project": "opspilot-full-test-f23-unit",
                "archive_root": str(root / "archives"),
                "key_root": str(root / "keys"),
                "lock_timeout_seconds": 0,
            }
        )
    )
    with Store(config):
        second = Store(config)
        with pytest.raises(OSError):
            with second:
                pytest.fail("Concurrent operations must never enter the same store")
        assert second.lock.closed
    with Store(config):
        pass  # The previous process/handle no longer owns the lock.

"""Restore a local Full rehearsal dump without exposing plaintext on the host."""

import argparse
import json
import os
import subprocess
import time
from pathlib import Path
from uuid import UUID

from cryptography.fernet import Fernet, InvalidToken


def docker(*args, data=None):
    result = subprocess.run(
        ["docker", *args],
        input=data,
        capture_output=True,
        timeout=120,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
    if result.returncode:
        raise RuntimeError(f"Docker {args[0]} operation failed ({result.returncode})")
    return result.stdout


def query(container, database, sql):
    return (
        docker(
            "exec",
            container,
            "psql",
            "-XAt",
            "-v",
            "ON_ERROR_STOP=1",
            "-U",
            "ops_migration",
            "-d",
            database,
            "-c",
            sql,
        )
        .decode()
        .strip()
    )


def snapshot(container, database):
    tables = json.loads(
        query(
            container,
            database,
            """
        SELECT json_agg(format('%I.%I', schemaname, tablename) ORDER BY schemaname, tablename)
        FROM pg_tables WHERE schemaname NOT IN ('pg_catalog', 'information_schema')
    """,
        )
    )
    result = {}
    for table in tables:
        result[table] = json.loads(
            query(
                container,
                database,
                f"""
            SELECT json_build_object('rows', count(*), 'sha256',
                encode(sha256(COALESCE(string_agg(convert_to(to_jsonb(t)::text, 'UTF8'),
                    ''::bytea ORDER BY convert_to(to_jsonb(t)::text, 'UTF8')), ''::bytea)), 'hex'))
            FROM {table} t
        """,
            )
        )
    return result


def assert_fixture(container, database, fixture):
    pending, committed = (UUID(fixture[k]) for k in ("pending", "committed"))
    assert (
        query(
            container,
            database,
            f"""
        SELECT count(*) FROM workflow.agent_runs r
        WHERE r.id = '{pending}' AND r.status = 'waiting_for_approval' AND EXISTS (
            SELECT 1 FROM checkpoints.checkpoint_writes w
            WHERE w.thread_id = r.id::text AND w.channel = '__interrupt__'
        )
    """,
        )
        == "1"
    )
    assert (
        query(
            container,
            database,
            f"""
        SELECT count(*) FROM workflow.actions a JOIN domain.tickets t
          ON t.originating_action_id = a.id
        WHERE a.run_id = '{committed}' AND a.execution_status = 'succeeded'
          AND a.execution_result->>'ticket_id' = t.id::text
    """,
        )
        == "1"
    )


def version(container, database):
    return query(container, database, "SELECT version_num FROM workflow.alembic_version")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("backup", "restore", "smoke-copy"))
    parser.add_argument("project")
    args = parser.parse_args()
    if not args.project.startswith("opspilot-full-test-f23-"):
        parser.error("F23 project required")
    project = args.project
    source = project + "-postgres-1"
    target = project + "-restore-postgres-1"
    source_db = "opspilot_full_test"
    target_db = "opspilot_full_recovered"
    base, candidate = "0020_prometheus", "0021_worker_admission"
    directory = Path(".tools/f23") / project
    fixture = json.loads((directory / "fixture.json").read_bytes())
    key = directory / "keys" / "backup.key"
    archive = directory / "backups" / "baseline.dump.enc"
    evidence = directory / "snapshot.json"
    if args.mode == "backup":
        assert version(source, source_db) == base
        assert_fixture(source, source_db, fixture)
        before = snapshot(source, source_db)
        key.parent.mkdir()
        archive.parent.mkdir()
        with key.open("xb") as handle:
            handle.write(Fernet.generate_key())
        dump = docker("exec", source, "pg_dump", "-Fc", "-U", "ops_migration", source_db)
        with archive.open("xb") as handle:
            handle.write(Fernet(key.read_bytes()).encrypt(dump))
        evidence.write_text(json.dumps(before), encoding="utf-8")
        return

    if args.mode == "smoke-copy":
        # This project contains synthetic data and the candidate DB remains available.
        assert version(source, source_db) == candidate
        query(source, "postgres", f"ALTER DATABASE {source_db} RENAME TO f23_candidate")
        query(source, "postgres", f"CREATE DATABASE {source_db} TEMPLATE template0")
        docker(
            "exec",
            "-i",
            source,
            "pg_restore",
            "--exit-on-error",
            "--single-transaction",
            "-U",
            "ops_migration",
            "-d",
            source_db,
            data=Fernet(key.read_bytes()).decrypt(archive.read_bytes()),
        )
        assert_fixture(source, source_db, fixture)
        assert version(source, source_db) == base
        return

    start = time.monotonic()
    assert version(source, source_db) == candidate
    before = json.loads(evidence.read_text(encoding="utf-8"))
    # The candidate migration changes the worker-slot function and the schema version.
    assert {
        k: v for k, v in snapshot(source, source_db).items() if k != "workflow.alembic_version"
    } == {k: v for k, v in before.items() if k != "workflow.alembic_version"}
    network = docker("inspect", target, "--format", "{{.HostConfig.NetworkMode}}").strip()
    assert network == b"none"
    assert (
        query(
            target,
            target_db,
            "SELECT count(*) FROM pg_tables "
            "WHERE schemaname NOT IN ('pg_catalog','information_schema')",
        )
        == "0"
    )
    encrypted = archive.read_bytes()
    cipher = Fernet(key.read_bytes())
    try:
        Fernet(Fernet.generate_key()).decrypt(encrypted)
    except InvalidToken:
        pass
    else:
        raise RuntimeError("Backup accepted an unrelated key")
    docker(
        "exec",
        "-i",
        target,
        "pg_restore",
        "--exit-on-error",
        "--single-transaction",
        "-U",
        "ops_migration",
        "-d",
        target_db,
        data=cipher.decrypt(encrypted),
    )
    query(target, "postgres", f"ALTER DATABASE {target_db} SET default_transaction_read_only = on")
    assert query(target, target_db, "SHOW transaction_read_only") == "on"
    roles = "ops_workflow", "ops_domain", "ops_checkpoint", "ops_identity", "ops_ingress"
    role_list = ", ".join(f"'{role}'" for role in roles)
    assert query(
        target,
        target_db,
        f"SELECT count(*) FROM pg_roles WHERE rolname IN ({role_list}) AND NOT rolcanlogin",
    ) == str(len(roles))
    assert version(target, target_db) == base
    assert_fixture(target, target_db, fixture)
    assert snapshot(target, target_db) == before
    function = (
        "SELECT pg_get_functiondef('workflow.worker_slot(uuid,boolean,uuid[])'::regprocedure)"
    )
    assert "pg_advisory_xact_lock(1801202621)" in query(source, source_db, function)
    assert "pg_advisory_xact_lock(1801202617)" in query(target, target_db, function)
    result = {
        "project": project,
        "baseline_schema": base,
        "candidate_schema": candidate,
        "recovered_schema": base,
        "backup_encrypted": True,
        "wrong_key_rejected": True,
        "backup_bytes": len(encrypted),
        "restore_database": target_db,
        "restore_network": "none",
        "restore_default_read_only": True,
        "workers_on_restore": 0,
        "matching_table_counts_and_hashes": len(before),
        "pending_interrupts_preserved": 1,
        "committed_ticket_and_receipt_preserved": 1,
        "synthetic_fixture_duplicate_decision_effects": 0,
        "restore_worker_replay_tested": False,
        "candidate_reverted_by_restore_to_fresh_database": True,
        "database_restore_and_verification_seconds": round(time.monotonic() - start, 2),
    }
    (
        Path(os.environ.get("F23_EVIDENCE_DIR", "docs/full/evidence/f23")) / "recovery.json"
    ).write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result))


if __name__ == "__main__":
    main()

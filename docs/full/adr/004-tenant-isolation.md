# ADR 004 — tenant ownership and administrative checkpoint schema

Status: accepted, F02, 2026-10-26.

Use non-null tenant keys, composite foreign keys and FORCE RLS together with explicit repository
filters. Bind trusted tenant context per SQLAlchemy transaction; never retain a previous request's
scope in a pooled connection. Repository sessions cannot switch tenant, including identity-map gets.
Global identity records remain unavailable to runtime roles until the scoped BFF is designed in F03.

Checkpoint rows also belong to tenants and reference registered tenant/run threads. Freeze the locked
SDK schema in an administrative Alembic migration; transfer table/schema ownership away from the
runtime checkpoint role and give only DML/read-version access. Use dedicated scoped saver connections,
not runtime DDL. An SDK migration-level mismatch stops execution. F06 must separately add epoch fencing.

Until F03/F04, API/MCP use explicitly configured local synthetic scope, not an unverified tenant header.
A client/config scope mismatch fails before network calls. No public/pilot auth claim is made.
Unknown legacy ownership blocks the transaction; a guessed/default tenant is not a migration strategy.
Consequences: every new tenant-owned relation needs a composite FK/RLS policy; every SDK upgrade needs
an explicit migration. The migration role remains privileged and outside the runtime threat boundary.

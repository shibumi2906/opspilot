# ADR 001-ownership

Status: accepted design for staged implementation, 2026-10-26.

PostgreSQL is authoritative for jobs/leases/commands/receipts. API will enqueue, workers will execute. Per-run epoch must fence snapshot, checkpoint and reservation writes in the same DB transaction. LangGraph persistence alone does not supply ownership. F05 adds jobs; F06 must prove a fenced saver with stale-worker tests before multiworker rollout. Existing API execution remains single-owner F01 baseline.

Consequence: later stages must provide live negative/recovery evidence; this ADR alone does not close their gates.

# ADR 002-graph-versioning

Status: accepted design for staged implementation, 2026-10-26.

Pin workflow/schema/policy versions on each new run. A deploy either keeps the previous graph until drain or applies a tested explicit state migration. Unsupported checkpoints stop in needs_attention without writes. Checkpoint reducers upsert stable IDs; interrupt replay must not perform effects. F01 contract is full-v1-draft/schema 1; runtime still uses inherited graph/schema, not the future Full schema.

Consequence: later stages must provide live negative/recovery evidence; this ADR alone does not close their gates.

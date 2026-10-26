# ADR 003-permissions

Status: accepted design for staged implementation, 2026-10-26.

OIDC authenticates identity; server memberships authorize tenant roles. Operator creates own investigations, approver decides within tenant, auditor reads redacted tenant history, admin manages membership/connectors without bypassing action policy. Pilot self-approval defaults denied. MCP service authentication is distinct from signed per-revision action authority. Browser OIDC tokens and provider credentials never become general MCP tokens. F03/F04/F09 implement these boundaries; F01 is local synthetic only.

Consequence: later stages must provide live negative/recovery evidence; this ADR alone does not close their gates.

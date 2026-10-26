# Full contracts — design baseline, schema 1

These contracts guide F02–F17; F01 exposes only the inherited V1 API. No V2 routes are claimed implemented.
The normative endpoint matrix and DTO fields are in specification §7; MCP fields in §8.

| Boundary | Required contract |
| --- | --- |
| Identity → core | Verified (issuer, subject), live session and tenant membership; caller text/headers cannot grant tenant access |
| API command | Opaque UUIDs, command_id/client_request_id, expected_version; identical replay returns saved result, changed payload 409 |
| Snapshot | schema_version, optimistic version, latest_event_id, status and separate outcome, bounded public evidence/actions/usage/report |
| Error | {schema_version, code, message, retryable, request_id}; no raw provider response, stack, secret or DSN |
| Action revision | Immutable logical_action_id/revision_id, tenant/run, tool, connector/target, exact arguments/hash, evidence/preconditions/dependencies, TTL |
| Approval decision | decision + expected_version + command_id only; caller cannot mutate approved arguments |
| MCP read | Strict registry/schema, scoped context, bounded provenance with observed_at/source/version/hash; unknown is not healthy |
| MCP write | Independent signed authority and persisted approval/epoch checks; exact normalized payload hash; atomic receipt + local effect |
| Verification | Read actual target fields and origin operation; verified only on exact match; unknown/mismatch never triggers blind write retry |
| Event | unique(run_id, sequence), event UUID, tenant, schema/snapshot versions, timestamp, redacted bounded payload; transactional replay source |

create_ticket approves customer/backend/connector/project/title/description/priority/evidence.
add_ticket_comment approves a concrete existing ticket/backend/body/evidence.
notify_manager approves a concrete tenant internal recipient/customer/body/evidence.
A new ticket ID requires a new comment revision and separate approval wave.
No URL, credential or arbitrary recipient supplied by a model becomes authority.

Status, execution and verification are independent: succeeded effect can have mismatch/unavailable verification.
Unknown dispatch is reconciled with reads, not resent. Cancellation cannot undo accepted effects.
Permissions, membership, TTL/freshness and ownership are rechecked before dispatch, not frozen in graph state.
Public V1 compatibility must enforce V2 authorization or return 410 by F04; MVP V1 remains separate.

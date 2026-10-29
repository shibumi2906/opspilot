# F13 security contracts

Scope: authenticated read-only SSE; DB events remain authoritative. No new mutation or migration.
Assets are private run/history metadata and session-scoped reference cursors. The browser is
untrusted; the API checks the identity store and the existing tenant/owner/role boundary, and
workflow DB reads retain FORCE RLS. No new outbound destination or durable private-payload store.
The stream cannot dispatch an action. Tampering, cross-scope replay, stale authorization,
compaction/gaps, slow consumers and physical-lease loss are the changed threat cases.
Cookie authentication only; SSE selected explicitly with Accept: text/event-stream.
Existing F07 bounded JSON replay remains the default, with its unchanged scoped pagination
reference protocol. SSE accepts no token or cursor in URL. Signed v1 cursors bind session,
actor, tenant and run; MAC uses the existing session-signing key, separate from service/grant keys. Public event envelopes expose
only type/sequence/schema/timestamp; snapshot uses the existing allowlisted DTO.

Before replay and each batch: uncached session, disabled-user, expiry, selected tenant and
object/role authorization; 5 s operation deadline. Recheck every 1 s, send deadline 3 s.
Established-stream worst-case detection + access_lost + final body: auth5 + query5 + send3 +
sleep1 + lease1 + auth5 + send3 + final send3 =26 s (excluding scheduling jitter).
Failure closes with access_lost and client clears private state. No session activity touch.

DB advisory connection reservations: global 8, tenant 4, actor 2 across API processes sharing
Full DB. Dedicated pool, physical disconnect releases reservations on crash; no Redis dependency.
A one-second physical-lease health check before every batch/event closes a stream when its
advisory connection is lost; it cannot silently continue without a reservation after DB restart.
Replay 64 events/batch, maximum lag 256, frame <=16 KiB; gaps/compaction/future cursor require
reset and authoritative snapshot. No unbounded producer queue; send timeout disconnects slow
clients. Heartbeats carry no business ID. Client deduplicates monotonic sequence, reconnects
with Last-Event-ID header, refreshes snapshot after reset; polling fallback bounded to 5 s.

SEC-01/10 regression/supply-chain gates and SEC-02/07/08 scoped evidence required.
Full ASVS L2 remains NOT_MET; F14/F15/F17/F23/F24 ownership is unchanged.

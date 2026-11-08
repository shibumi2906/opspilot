# F21 resilience scope and acceptance

2026-11-08; base152d59b; Ops checkout/codex/opspilot-full. Scripted local evidence only.
The owner explicitly requested F21 while F20 is incomplete and deferred real Jira checks.
This authorizes F21 work; it does not close F20, vendor-write recovery, Pilot or full L2.

## Runtime changes

Migration0021 changes only the advisory-lock key inside the existing SECURITY DEFINER
`workflow.worker_slot(uuid,boolean,uuid[])`. It checks that exactly one expected old
lock statement exists before replacing it. All tenant/actor/fairness/cap predicates,
function identity/owner/ACL and search_path remain inherited. Admission stays globally
serialized on1801202621. Runtime/SDK transactions still take shared lifecycle lock
1801202617; administrative compaction retains its exclusive counterpart. The previous
upgrade from shared maintenance lock to exclusive admission lock caused nested approval/
checkpoint readers to queue behind a writer that needed their outer transactions to end.
No statement/idle timeouts or authorization checks were relaxed.

Queued API creation now borrows `RunService.engine` rather than allocating a pool for
each HTTP request. The graph creator disposes only an engine it owns. The API lifespan
still closes its shared pool. Direct graph/CLI callers retain their owned-engine path.
Trusted tenant/actor/fence transaction-local bindings remain applied on every transaction.
The previous100-distinct-request burst exhausted PostgreSQL connection slots before
admission could return all bounded denials; the failed attempt remains in evidence.

Health accepts the two explicitly compatible schemas0020 and0021 for a rolling upgrade.
It does not accept arbitrary future schemas. Main Full/0019 and its images were not
upgraded, rebuilt, reseeded or migrated as part of these isolated labs.

## Measured workload

`tests/f21_lab.py` starts two real uvicorn processes and two native worker processes
against one isolated PostgreSQL, MCP, Redis, collector and F21-only TLS secrets manager.
HTTP sessions use the existing explicit test fixture. This exercises BFF session/CSRF/
role behavior; it does not claim IdP login throughput, service quorum or HA.

The initial burst sends100 simultaneous create requests for20 identities (five replays
each), observes20 concurrently nonterminal runs, and sends100 simultaneous decisions.
Ten actions are approved and ten rejected; cross-tenant reads must return404. Active
means accepted nonterminal work, including queue/human wait, not20 simultaneous worker
execution slots. A second burst sends100 distinct create identities, exercising actual
admission limits32 actor/40 tenant/64 global; admitted runs are rejected to prove0 effects.
These are test limits, not a product throughput or latency promise.

The soak schedules100 additional runs, two per36-second period, for at least1800 real
seconds. Start/resume jobs must be counted independently after the run; burst/quota jobs
must not be substituted for the required200 soak jobs. A separate approval is left
waiting through the real soak to exercise expiry rather than inheriting old consent.
The runner injects API/worker SIGKILL and replacement; the controller stops/restores only
its labelled F21 MCP, Redis, collector and PostgreSQL containers, one at a time. A6-second
service stop is not a network partition or upstream-side write cancellation guarantee.

The final DB audit checks exact title/description/priority/evidence/customer fields,
approval ownership, duplicate action receipts and cross-tenant associations. Seed
exceptions use their exact trusted UUIDs, never a user-controlled title. All accepted
commands must finish or explicitly need attention with a reason. Nonterminal or unsafe
outcomes fail acceptance. Measured failures/retries remain visible, not omitted from
latency samples for accepted replay/paced create/decision cycles. The quota burst has its own explicit100-request status denominator and is not included in those latency samples. Completion latency covers paced soak cycles. Scripted cost and vendor registrations are independently checked.

## Fault and security coverage

New integration probes cover admission lock inversion, shared pool ownership,100-way
opposite decision/cancel races across two API processes, session revocation, operator
denial, foreign-tenant reads, worker restart with pinned v1/v2 and expired approval wait.
Inherited dedicated process tests are rerun for API commit-before-response loss,
worker kill/stop/DB-proxy partition, grant/freshness/replay/expiry and durable budgets.
Results are recorded only after execution; historical evidence is not a fresh pass.

SEC-02/03/05/07/09/11 and common SEC-01/10 apply. All253 inherited ASVS identities,
levels, assessments, accountable owners and N/A fields remain protected. Stage-local
evidence does not close complete requirements. F20 Jira dispatch/one-attempt/reconciliation
is not implemented and cannot be fault-tested here; that dependency remains NOT_MET.
No real Jira requests, paid calls, remote CI or push are authorized by this lab.

## Isolation and reproduction

Use `scripts/test-full-f21.ps1 -Mode Prepare/Smoke/Load/Faults/Stop` only with an
`opspilot-full-test-f21-*` project. The accepted project/subnet is recorded in evidence.
The shell controller verifies exact project/service labels before any outage. A shared
F17-manager attachment was rejected by automatic approval review and never executed.
The replacement creates a new manager with independent ignored credentials/volumes and
only its own lab network, without expanding existing F17/dev manager connectivity.

No images are rebuilt on this disk-limited host. Existing F19 images provide pinned
libraries; current application sources/migrations and new tests are read-only mounts,
explicitly added to PYTHONPATH. This is a source-mounted test artifact, not a new released
image. Failed labs/reports/volumes are preserved. Refresh only the dedicated F21 manager
tokens before a long run; they have a one-hour TTL and keys are preserved on refresh.
Stop only F21 resources after verification, preserving volumes and existing projects.


## Profile distinctions

The final load profile is r4/subnet30. Fault suites run serially afterward in a fresh
r6/subnet32 database so deliberate stale-lease/negative fixtures cannot taint soak counts.
The r5 candidate correctly rejected an attempted test-fixture mutation of immutable
approval expiry. Its failed report is retained; the corrected fixture configures a
10-second TTL before creating revisions and waits for natural expiry. No guard was relaxed.
Legacy fault fixtures use their inherited1000/5000/10000 active-run caps to accommodate
intentionally retained waiting probes; load/admission evidence remains the separate
32/40/64 profile. Requirement-specific quota tests keep their own bounded low limits.
The dedicated fencing fixtures run last because they intentionally preserve stale claims.
Use a separate fresh r7/subnet33 database for this final fencing suite. The initial
r6 attempt could not obtain the target claims within20 seconds after the broad negative
fixtures; its three failures remain in attempts/fencing-r1.xml. No claim timeout,
fairness predicate, lease guard or existing fixture is weakened to make the suite pass.
Worker `replacement_seconds` records process spawn only; API replacement includes health
readiness. These are not identical recovery metrics; inspect completion latency and the
claimed-job fencing probes for durable recovery evidence.

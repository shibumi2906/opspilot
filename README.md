# OpsPilot

Portfolio MVP: controlled operational incident investigation. Implementation in progress. Stages 1–4 are implemented.

Implemented: stages 1–4 (foundation, MCP diagnostics, checkpointed investigation and approval) (see [implementation status](docs/implementation-status.md) for actual verification).
Ticket execution and UI are future stages. All business data is synthetic.

## Initialize the local database

PostgreSQL is a real local Docker database, included in stage 1. The `opspilot` database,
roles and schemas are created when the postgres service initializes its persistent volume.
Alembic creates/updates application tables; seed adds synthetic demo data. Stage 3 adds SDK
checkpoint tables in the separate `checkpoints` schema. No external database is required.

After creating `.env` and filling the database passwords and MCP token as described below:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/setup-local.ps1
```

This builds runtime images, starts PostgreSQL, applies migrations, seeds data, initializes
checkpoints with the restricted checkpoint role and starts API/MCP. It is repeatable and
preserves the volume and unrelated records; seeded demo records are upserted to fixture values.
Use `-SkipBuild` only if images already match the source. No LLM calls are made by setup.
The isolated `opspilot_test` database/volume is created separately by the test scripts.

## Stage 1 quickstart

Prerequisite: Docker Desktop with Linux containers and Docker Compose.

```powershell
Copy-Item .env.example .env
```

Fill every secret in `.env` with a separate random 64-character hex string. For example,
generate each value with `python -c "import secrets; print(secrets.token_hex(32))"`.
Never commit `.env`. Passwords must use hex characters to remain URL-safe.

```powershell
docker compose build
docker compose up -d --wait postgres
docker compose run --rm admin
docker compose run --rm admin python -m opspilot.cli.seed
docker compose run --rm admin python -m opspilot.cli.seed
docker compose up -d mcp api
docker compose exec api python -m opspilot.cli.mcp_smoke
```

Health: http://127.0.0.1:8000/health (200 when database, migrations and MCP are ready).
API uses a restricted workflow role; MCP uses a separate domain role. Neither PostgreSQL
nor MCP publishes a host port. Admin is an explicitly invoked one-shot tools service.
Discovery exposes eight read-tools; `create_ticket` is not registered. No LLM/API key required.

`docker compose down` preserves database data. Init SQL runs only on a new volume;
changing passwords in `.env` does not change credentials in an existing database.
Do not remove database volumes to fix transient startup errors.

## Development

Python 3.12 and uv 0.13.1. `uv sync --frozen`, `uv run ruff check .`, `uv run mypy src`,
`uv run pytest tests/unit`. Integration tests require the isolated stack documented in
docs/implementation-status.md and refuse to run against the regular demo database.

Run the complete stage 1 test suite in an isolated Docker stack:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/test-stage1.ps1
```

The script uses `opspilot-test`, its own volume and `opspilot_test` database, then stops
its containers. It leaves the demo stack and its data intact. Test failures are returned
as a nonzero exit code. Pinned versions and the negotiated MCP protocol are recorded in
[dependencies](docs/dependencies.md).

The authoritative scope and eight implementation stages are in
[OpsPilot_Portfolio_MVP_plan.md](OpsPilot_Portfolio_MVP_plan.md).

## Stage 2 diagnostics

For an existing stage 1 installation, rebuild, apply the new migration and recreate services:

```powershell
docker compose build
docker compose up -d --wait postgres
docker compose run --rm admin
docker compose up -d mcp api
docker compose exec api python -m opspilot.cli.diagnose GreenShop --language ru
docker compose exec api python -m opspilot.cli.diagnose GreenShop --language en
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/test-stage2.ps1
```

The CLI uses real MCP reads without an LLM. JSON includes source references, deterministic
content hashes/evidence IDs, current observations, historical incidents and runbook excerpts.
`Green` returns `insufficient_context` with candidates. Empty search is a successful empty
list; an absent ticket returns `NOT_FOUND`. Diagnostics never create tickets.

Search supports optional `language` (`ru`/`en`), integration type and incident customer
filters; PostgreSQL full-text ranking uses language-specific GIN indexes and stable tie
breaks. Query is 1–500 characters; search/customer limits are 1–10. Event windows are
half-open `[from, to)`, timezone-aware, positive and at most seven days; event limit is 1–100.

Set trusted `SCENARIO_ID` in `.env` to `greenshop_expired` (default), `healthy`, `unknown`,
`timeout` or `contradictory`, then recreate `mcp` and `api` to select an overlay. Tool
arguments cannot select scenarios. Timeout is `MONITORING_TIMEOUT`, with no evidence;
unknown is a successful observation. Contradictory reports preserve healthy status together
with 401 events. Overlays change no database fixtures. Non-GreenShop integrations use
healthy synthetic observations; the timeout overlay makes monitoring unavailable.

The stage 2 script runs all current tests in the same isolated test stack as stage 1.

## Stage 3 investigation

After building/applying migrations as above:

```powershell
docker compose exec api python -m opspilot.cli.run "Investigate why GreenShop orders fail today" --mode scripted
docker compose exec api python -m opspilot.cli.run "Check GreenShop status" --mode scripted
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/test-stage3.ps1
```

This runs a real LangGraph StateGraph with conditional edges and an investigation loop.
PostgreSQL checkpoints are initialized in `checkpoints` before invocation; thread_id=run_id.
CLI output includes mode, model ID, evidence-linked facts/hypotheses, budget counters and
at most one ticket proposal. Since stage 4, actionable investigations pause at approval;
`proposed_only` was the stage-3 checkpoint outcome. No ticket is executed in stage 4.
MCP discovery still exposes exactly eight read-tools. Runs are stored in `workflow.agent_runs`.

Use `--client-request-id <UUID>` to retrieve an existing identical invocation without
re-running it. Reusing that ID with different request/configuration returns a conflict.
Stage 4 adds API background runs and approval resume; automatic crash recovery remains stage 7.

Scripted mode makes fixture provider decisions, retaining real graph/MCP/database calls.
It supports RU/EN fixture requests, known customer names, `customer <name>`, status-only,
and today relative to the scenario clock in Asia/Jerusalem. Real mode lets the model select
read-tools and arguments; code enforces allowlist/scope/schema checks and budgets.

For real mode add these entries to the local ignored `.env` file:

```dotenv
OPENAI_API_KEY=<your-local-key>
OPENAI_MODEL=gpt-5.6-terra
OPENAI_REASONING_EFFORT=low
LLM_MODE=scripted
```

`OPENAI_MODEL` is an explicit API model ID; no automatic substitution occurs.
Recreate API to load updated values, then invoke real mode explicitly:

```powershell
docker compose up -d --force-recreate api
docker compose exec api python -m opspilot.cli.run "Investigate why GreenShop orders fail today" --mode real
```

The OpenAI Responses REST adapter uses function calling for read selection and strict
structured outputs for classification, analysis and planning. Only API receives the LLM key;
MCP and admin do not. Full provider responses, credentials and hidden reasoning are not logged
or checkpointed. The suite mocks provider HTTP and makes no paid calls.

Limits (recorded per run): rounds=6, read attempts=15 (one reserved for future verification,
so at most 14 diagnostic attempts), model attempts=10, measured input+output tokens=30000,
active processing=120 seconds, recursion_limit=60, proposals=1. Configure lower limits with
`AGENT_MAX_ROUNDS`, `AGENT_MAX_READS`, `AGENT_MAX_LLM_ATTEMPTS`, `AGENT_MAX_TOKENS`,
`AGENT_ACTIVE_SECONDS`. Read timeout=5s/max 3 attempts; model timeout=30s/max 2 attempts,
including invalid-output correction. Attempts count even on failure. Known token totals
and unknown_usage_count are separate. Timeouts are capped by remaining active time.
Status-only, missing/ambiguous customers, unknown/timeout/contradictory monitoring and
policy/budget violations cannot produce a ticket proposal.

## Stage 4: durable approval and decisions

Start the updated API/MCP with `scripts/setup-local.ps1`. The API supports one process;
`uvicorn --workers > 1` is unsupported. A PostgreSQL session advisory lock rejects a
second API process before it modifies workflow state. Different runs have separate locks;
one run cannot be invoked/resumed concurrently. Background task failures become failed snapshots.

```powershell
$body = @{ request = 'Investigate GreenShop'; client_request_id = [guid]::NewGuid().ToString() } | ConvertTo-Json
$run = Invoke-RestMethod http://127.0.0.1:8000/api/v1/runs -Method Post -ContentType application/json -Body $body
$snapshot = Invoke-RestMethod ("http://127.0.0.1:8000" + $run.snapshot_url)
# Poll GET until status=waiting_for_approval, then inspect snapshot.action.arguments.
$decision = @{ action_id = $snapshot.action.action_id; decision = 'reject' } | ConvertTo-Json
Invoke-RestMethod ("http://127.0.0.1:8000/api/v1/runs/" + $run.run_id + "/decision") -Method Post -ContentType application/json -Body $decision
```

Use `approve` for the other branch. Reject completes with `rejected`; Approve completes
with `partial` and `execution_not_implemented`. Both leave tickets unchanged. The saved
card remains visible after either decision; execution_status stays `not_started` and no
report claims ticket creation or restored orders. Real ticket execution belongs to stage 5.

POST returns 202 after saving the queued run. Polling reads a public snapshot, without raw
checkpoint data. Reusing client_request_id with identical input returns the same run;
changed input returns 409. Decisions accept only action_id and approve/reject: extra
arguments return 422, missing action/run returns 404, another run's action or an opposite
recorded decision returns 409. A repeated completed decision returns 200, otherwise 202.
The graph pauses with a real persisted interrupt and resumes the original thread using
only the action reference; the approval node independently reads the stored decision.

CLI investigation also pauses at approval:

```powershell
docker compose exec api python -m opspilot.cli.run "Investigate GreenShop" --mode scripted
docker compose exec api python -m opspilot.cli.run --run-id <run_id> --action-id <action_id> --decision reject
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/test-stage4.ps1
```

CLI is a local administrative alternative: avoid invoking it concurrently with API operations
on the same run. Recovery across API crashes and automatic restart handling remain stage 7;
stage 4 supports ordinary pause/resume while the API is running. Never delete checkpoint
or workflow records to retry a decision.

# OpsPilot

Portfolio MVP: controlled operational incident investigation. Implementation in progress.

Implemented: stages 1–2 (foundation and MCP diagnostics) (see [implementation status](docs/implementation-status.md) for actual verification).
LangGraph, approvals, ticket execution and UI are future stages. All business data is synthetic.

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

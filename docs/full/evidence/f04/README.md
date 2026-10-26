# F04 evidence

2026-10-26; codex/opspilot-full; base 75367f9cd869b213aa3ac86dfd844ac8b101cd12, dirty implementation snapshot.
Commit subject: feat(full): enforce F04 API and scoped MCP authorization.
Worktree: C:/Users/user/.codex/worktrees/opspilot-full-f01/AI Incident & Operations Agent.

Stage command: `powershell -NoProfile -File scripts/test-full-f04.ps1`.
Main backend: 200 passed, 7 dedicated migration/recovery skips. Browser: 12 passed. Dedicated API
hard restart: 3 passed. Scripted inherited regression evals: 12/12, hard safety gate true.
Ruff/format pass; mypy passes in 95 source files. There are no paid model/vendor calls or remote CI claims.

Two tenants complete their own GreenShop investigation → separate operator/approver → real MCP
write → exact read verification. A real OIDC browser also approves/verifies tenant B then proves its
UUID is hidden after switching to A. Matrix covers operator/approver/auditor/admin/unassigned,
foreign/same-tenant other actor UUID/evidence/actions/checkpoints, actor-filtered counts, HMAC cursor
binding, forged tenant header/tool args, closed V1, admin scope/self-escalation, service-bearer-only,
OIDC token passthrough, read-context writes and an approver revoked before dispatch. Key tests use
real Ed25519 and an actual MCP HTTP fixture accepting next and rejecting a retired key.

The first write gate found PostgreSQL row-lock privileges were broader than SELECT. The final
migration uses a scope-checked definer read/lock helper, with no runtime UPDATE grant. It was tested
in the synthetic test DB, then applied through the final Alembic upgrade to dev Full from schema 0004.
[Live runtime-role lock smoke](role-lock-smoke.json) proves own-scope true, foreign false, UPDATE false.

After the main suite, the final 17 auth/identity cases were repeated after minimizing MCP credentials
and closing pre-lookup missing-tenant denial, actor-bound request-key replay and the V2 snapshot URL.
Command with the standard Full test Compose prefix:
`run --rm --no-deps tests python -m pytest -p no:cacheprovider -q tests/integration/test_authorization.py tests/integration/test_mcp_key_rotation.py tests/integration/test_identity.py`.
These are 17 repeated cases, not an extra denominator. Final Ruff and mypy were repeated too.

Live Full: only its web/api/mcp were stopped for migration 0005; local bootstrap ran, and
`docker compose -p opspilot-full -f compose.full.yaml up -d --wait postgres oidc collector jaeger mcp api web`
returned running/ready services. UI 8091 and API 8011/health returned 200. Scoped CLI SDK smoke:
`run --rm --no-deps api python -m opspilot.cli.mcp_smoke` negotiated MCP 2025-11-25, discovered nine
tools, read GreenShop and returned NOT_FOUND for an unknown customer. Docker inspection confirms
MCP receives only the read-only public key directory and no BFF signing secret/private key mount.

[Counts](checks.json), [case details](evals/scripted.json), [eval summary](evals/scripted.md),
[MVP preservation](mvp-isolation.json). Raw ignored logs: .tools/f04-checks.log,
f04-final-authority.log, f04-live-sdk.log. MVP source/media/.env, main/HEAD, four images and volumes
match the saved baseline; no MVP service was restarted, migrated or built. Full test project stopped
without removing volumes; dev Full remains running with isolated resources.

Implemented V2 subset/limits and key lifecycle: [authorization.md](../../authorization.md).
Future approval revisions/TTL, clarification/cancel/SSE, full admin UI and connectors are not claimed.
Background execution remains in API; F05 durable jobs and F06 fencing were not started.

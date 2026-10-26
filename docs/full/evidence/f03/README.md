# F03 measured evidence

2026-10-26, branch codex/opspilot-full, base a65f702; dirty implementation snapshot.
Commit subject: feat(full): implement F03 OIDC sessions and tenant roles.
Canonical worktree: C:/Users/user/.codex/worktrees/opspilot-full-f01/AI Incident & Operations Agent.

Stage runner: `powershell -NoProfile -File scripts/test-full-f03.ps1`.
Backend: 178 passed, 7 dedicated migration/recovery skips. Final identity suite: 5 passed,
including one added identity-gateway privilege test and four repeated auth cases: 179 distinct backend cases.
Ruff and mypy pass (90 source files). JWT negative tests cover issuer/audience/signature/nonce/expiry/algorithm.
Session tests cover one-time state/binding, fixation, expiry, exact Origin/CSRF, logout, role removal,
tenant switching, no automatic membership, operator denial and strict/default versus labeled demo self-approval.

Real Keycloak 26.2.5 browser suite: 11 passed, including the original nine authenticated GreenShop
regressions and two real authorization-code/PKCE identity scenarios. No token endpoint mocks replace
this gate. A first browser run found a rapid tenant-switch/navigation race; the UI now blocks concurrent
identity mutations and the test waits for the first saved selection. All 11 passed after correction.
Opaque app cookie HttpOnly/SameSite flags, empty browser credential storage, revoked-cookie rejection,
two memberships and successful OIDC login without memberships were checked.

Manual continuation after the browser fix used the same Full test Compose prefix:
`docker compose -p opspilot-full-test -f compose.full.yaml -f compose.full.test.yaml`.
`run --rm e2e` → 11 passed; `stop api`, then
`run --rm --no-deps -e TEST_RECOVERY_API=1 tests python -m pytest -p no:cacheprovider -q tests/integration/test_api_restart.py`
→ 3 passed. `run --rm --no-deps evals python -m opspilot.evals.runner --mode scripted --commit a65f702 --dirty`
→ 12/12, hard safety gate true. Final `tests python -m pytest ... tests/integration/test_identity.py`
→ 5 passed; final `tests ruff check --no-cache src tests migrations` and `tests mypy --cache-dir /tmp/opspilot-mypy src` passed.
The full stage script includes these cases on subsequent runs. Test projects were stopped without volume deletion.

Live Full: stopped only its api/mcp/web, migrated admin to 0004_identity_sessions, ran
`admin python -m opspilot.cli.bootstrap_identity`, then started postgres/oidc/collector/jaeger/mcp/api/web.
API 8011/health and UI 8091 returned 200; issuer published only on 127.0.0.1:8181 with separate oidcdata volume.
The local identity password and session/issuer credentials were newly generated in ignored Full .env.
No MVP env, DB or credentials were copied. Dependency lock adds a direct declaration of the already
locked PyJWT/crypto dependency; frozen builds pass, package versions are unchanged.

[MVP fingerprint report](mvp-isolation.json), [counts](checks.json),
[case details](evals/scripted.json), [eval report](evals/scripted.md).
Raw local logs: .tools/f03-checks.log, f03-browser.log, f03-recovery.log, f03-focused.log, f03-evals.log.
No external model/provider calls or remote CI run. Keycloak uses intentional local HTTP dev mode;
Secure app cookies are selected for an HTTPS origin, not claimed exercised in a public pilot here.
Logout revokes the BFF session; IdP-wide SSO logout is not claimed. F04 will close/authorize V2 and MCP;
F05 jobs, F06 fencing and F23 production TLS remain unimplemented at this commit.

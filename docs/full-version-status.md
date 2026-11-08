# OpsPilot Full — статус реализации

Дата создания: 26 октября 2026 года. Обновлено: 8 ноября 2026 года. **F01–F19 завершены; F20 blocked, реальные Jira проверки отложены владельцем; F21 local resilience измерен, overall blocked на F20 и manager security finding; F22–F24 не начаты.**

Источник требований: [OpsPilot_Full_Project_Specification.md](../OpsPilot_Full_Project_Specification.md).
Portfolio MVP завершён отдельно; его статус — [implementation-status.md](implementation-status.md).
Опорный MVP-коммит: `01019b6`. Новый план не обнуляет прежние этапы 1–8.

## Где выполнять работу

Канонический tracker находится в Full checkout:
`C:\Users\user\Desktop\code\Ops`,
ветка `codex/opspilot-full`, planning base `f9f8d79f572a575dd0f86c40986e7ae13ebb45c9`.
В исходном MVP checkout создан игнорируемый `.tools/opspilot-full-workspace.json` с путём,
веткой, base_commit, compose_project и status_file, без credentials.
Исходная planning-копия tracker в MVP намеренно не меняется.

До проверки изоляции запрещены миграции, сборка образов и изменение приложения ради Full.
MVP `.env`, UI 8081, БД, volumes, images, source/media и ветка сохраняются.

Копия Ops подготовлена 30 октября 2026 года из F15 `4733998`. Это самостоятельный Git-репозиторий.
Предыдущий Full worktree сохранён по прежнему пути; новые этапы выполнять в Ops.
Путь к MVP берётся из ignored `.tools/opspilot-full-workspace.json → mvp_path`,
а не выводится из расположения `.git`. Подготовка workspace не начинает F16.

## Текущая очередь

**F19 завершён. F20 остаётся blocked; владелец отложил реальные Jira checks. По отдельному явному запросу проведены F21 local fault/concurrency/load/soak; общий статус blocked, см. evidence и security finding. F22–F24 не начинать автоматически. Full Pilot/ASVS L2 NOT_MET.**

По отдельному запросу пользователя выполнен локальный security baseline для ASVS L2 hardening F01–F08:
[security tracker](security/hardening/status.md). Это не начало F09 и не утверждение
о полном соответствии L2; локальный hardened-контур отделён от development Full и MVP.

Безопасность включена в очередь реализации: [обязательный план SEC-01–12](security/asvs-l2-implementation-plan.md)
и [backlog всех 253 ASVS IDs](security/asvs-l2-requirement-backlog.json).
F09 включает предварительные security contracts; F17/F23 не являются поводом отложить их
проектирование. Общие SEC-01/SEC-10 change gates обязательны для каждого нового этапа.
Функциональный done без security gates текущего этапа запрещён; полный L2 пока NOT_MET.

Команда для следующего этапа (пока не выполнять):

> Сделай F19 полной версии OpsPilot по OpsPilot_Full_Project_Specification.md, сохранив MVP.

Затем достаточно:

> Сделай следующий этап полной версии OpsPilot.

Исполнитель выбирает первый этап не в done, продолжает in_progress/blocked и не перескакивает
через него. Один этап — один проверенный результат и отдельный локальный коммит в Full.
Диапазон выполняется последовательно с отдельной проверкой и коммитом каждого этапа.

## Статусы

Разрешённые значения: `not_started`, `in_progress`, `blocked`, `done`.
`done` требует всех обязательных проверок, включая live evidence там, где они предусмотрены.
Наличие реализации на mocks не закрывает реальный connector/deployment/CI gate.
Если задача остановлена владельцем, записать причину в подробностях; не объявлять её done.

| ID | Статус | Результат этапа | Evidence / commit | Обязательные security-задачи |
| --- | --- | --- | --- | --- |
| F01 | done | Отдельные worktree/ресурсы Full, сохранённый MVP, baseline/contracts | [evidence](full/evidence/f01.md); commit subject: `feat(full): isolate F01 foundation and preserve portfolio MVP` | [SEC-00: local baseline](security/hardening/status.md) |
| F02 | done | Tenant schema/RLS/upgrade fixtures | [evidence](full/evidence/f02/README.md); commit subject: `feat(full): add F02 tenant isolation and safe fixture upgrades` | [SEC-00: local baseline](security/hardening/status.md) |
| F03 | done | OIDC, sessions, memberships/роли | [evidence](full/evidence/f03/README.md); commit subject: `feat(full): implement F03 OIDC sessions and tenant roles` | [SEC-00: local baseline](security/hardening/status.md) |
| F04 | done | Сквозная API/MCP authorization | [evidence](full/evidence/f04/README.md); commit subject: `feat(full): enforce F04 API and scoped MCP authorization` | [SEC-00: local baseline](security/hardening/status.md) |
| F05 | done | Durable jobs, отдельный worker | [evidence](full/evidence/f05/README.md); commit subject: `feat(full): implement F05 durable jobs and independent worker` | [SEC-00: local baseline](security/hardening/status.md) |
| F06 | done | Multiworker leases/fenced checkpoints | [evidence](full/evidence/f06/README.md); commit subject: `feat(full): implement F06 multiworker leases and fenced checkpoints` | [SEC-00: local baseline](security/hardening/status.md) |
| F07 | done | Transactional events/audit/projections | [evidence](full/evidence/f07/README.md); commit subject: `feat(full): implement F07 transactional events audit and projections` | [SEC-00: local baseline](security/hardening/status.md) |
| F08 | done | Durable typed clarification и cancellation | [evidence](full/evidence/f08/README.md); commit subject: `feat(full): implement F08 durable clarification and cancellation` | [SEC-00: local baseline](security/hardening/status.md) |
| F09 | done | Immutable revisions, version/TTL, independent signed persisted grants, exact MCP authorization | [evidence](full/evidence/f09/README.md); commit subject: `feat(full-f09): bind immutable revisions to signed execution grants` | [SEC-01/02/03/04/05/06](security/asvs-l2-implementation-plan.md) |
| F10 | done | Три local write-tools, atomic receipts, exact verification и tenant/object/recipient scope | [evidence](full/evidence/f10/README.md) | [SEC-03/06/08](security/asvs-l2-implementation-plan.md) |
| F11 | done | Bounded mixed DAG, independent decisions, sequential approved subset, dependent skip и concrete comment wave | [evidence](full/evidence/f11/README.md) | [SEC-03/07](security/asvs-l2-implementation-plan.md) |
| F12 | done | Uncached preconditions, DB-time expiry/revoke/roles, bounded replacement consent и durable verification quota | [evidence](full/evidence/f12/README.md) | [SEC-02/03/04](security/asvs-l2-implementation-plan.md) |
| F13 | done | Authenticated DB SSE/replay/reset, live revocation, bounded streams и browser reconnect | [evidence](full/evidence/f13/README.md) | [SEC-02/07/08](security/asvs-l2-implementation-plan.md) |
| F14 | done | Ролевой workspace, history/inbox/admin/audit, exact revision/TTL, scoped export | [evidence](full/evidence/f14/README.md) | [SEC-02/06/08](security/asvs-l2-implementation-plan.md) |
| F15 | done | Scoped Redis, durable quotas/fair admission, retry usage и versioned cost | [evidence](full/evidence/f15/README.md) | [SEC-07](security/asvs-l2-implementation-plan.md) |
| F16 | done | Protected traces/logs/metrics, durable job/epoch links и scoped operator diagnostics | [evidence](full/evidence/f16/README.md) | [SEC-05](security/asvs-l2-implementation-plan.md) |
| F17 | done | Retention/tombstones, scoped export, real manager rotation/recovery и локальный Full Core acceptance | [evidence](full/evidence/f17/README.md); commit subject: `feat(full): complete F17 lifecycle and Core security acceptance` | [SEC-04/05/06/10](security/asvs-l2-implementation-plan.md) |
| F18 | done | Manager-backed adapters, bounded HTTPS/circuit breaker, signed durable observation ingress и recovery | [evidence](full/evidence/f18/README.md); commit subject: `feat(full): complete F18 adapter platform and signed ingress` | [SEC-04/09](security/asvs-l2-implementation-plan.md) |
| F19 | done | Scoped Prometheus reads: local contracts plus actual owned AWS staging health, MCP/OIDC UI; temporary resources removed | [local evidence](full/evidence/f19/README.md); [AWS evidence](full/evidence/f19-aws/README.md); local base `c984d6a`; stage commit subject below | [SEC-09](security/asvs-l2-implementation-plan.md) |
| F20 | blocked | Authorized Jira sandbox writes/reconciliation | — | [SEC-03/09](security/asvs-l2-implementation-plan.md) |
| F21 | blocked | Local load/soak/recovery measured; F20 boundaries and manager HIGH remain | [evidence](full/evidence/f21/README.md); commit subject below | [SEC-02/03/05/07/09/11](security/asvs-l2-implementation-plan.md) |
| F22 | not_started | 50 evals и отдельный real/holdout report | — | [SEC-10/11](security/asvs-l2-implementation-plan.md) |
| F23 | not_started | Pilot deployment/TLS/backup/restore | — | [SEC-02/04/05/06/09/10/12](security/asvs-l2-implementation-plan.md) |
| F24 | not_started | Full Pilot release и traceability | — | [SEC-01/10/11/12](security/asvs-l2-implementation-plan.md) |

## Запись результата этапа

При выполнении обновлять таблицу и добавлять ниже запись по этому шаблону:

```text
FNN — название
Дата; абсолютный worktree path; branch; base SHA; workflow/policy/schema versions.
Что реализовано и какие требования спецификации закрыты.
Security: SEC IDs / ASVS IDs, scope delta, implementation/evidence/review/N/A/blockers в backlog.
Изменённые migration/code/UI/docs paths в Full checkout.
Проверки: точные команды, isolated project/database, результаты и report paths.
Изоляция MVP: какие source/config/image/volume fingerprints проверены; результат.
Внешние вызовы: только фактические destinations/scopes/authorization и известные расходы.
Blockers/limitations/remaining work — конкретно; без секретов и необработанных provider errors.
Evidence commit SHA либо subject этого же stage commit; не выдумывать будущий SHA.
Следующий этап или причина, почему текущий ещё не done.
```

## Проверки на момент создания плана

Проверены структура нового документа, наличие всех 24 stages, соответствие tracker и локальные
документационные ссылки. Новый application/test/LLM/deployment прогон не выполнялся: задача этого
изменения — спецификация. Прежние результаты MVP не выдаются за результаты Full.

## F01 — изоляция MVP и база Full

26 октября 2026. Worktree: `C:\Users\user\.codex\worktrees\opspilot-full-f01\AI Incident & Operations Agent`.
Ветка `codex/opspilot-full`; base SHA `f9f8d79f572a575dd0f86c40986e7ae13ebb45c9`.
MVP baseline/tag: `01019b69dbf0b300d2ab2a600089f19a638d2108`, `opspilot-portfolio-mvp-v1.0`.
Runtime graph blob `5ea9d96354e37e4b8c54719006e1ac0b836866f1`, policy blob
`7dddb49f221d157d8859295d2e85b28ae05e1824`; унаследованная schema `0002_search_indexes`.
Проектные Full contracts: `full-v1-draft`, schema_version 1; это ещё не runtime Full workflow.

Реализованы отдельные `.env`, setup, standalone Compose и все image tags `opspilot-full/*`,
проекты/volumes/БД `opspilot-full`/`opspilot_full` и `opspilot-full-test`/`opspilot_full_test`.
Порты UI 8091, API 8011 (8010 занят pinui-rag), Jaeger 16696; 8181 зарезервирован для F03.
DB guards проверяют DSN и фактический current_database; eval/test guards разрешают только Full test DB.
В Full перенаправлены также старые Compose/stage scripts/CI, чтобы они не затрагивали MVP.
Новых schema migrations и изменений domain/UI поведения нет.

Добавлены `docs/full/{architecture,contracts,state-transitions,compatibility}.md`, JSON-таблица
состояний с тестом и ADR ownership, graph versioning, permissions. MCP SDK smoke использует
настоящий Streamable HTTP transport, protocol 2025-11-25, реальный PostgreSQL и LangGraph.

Проверки и точные команды: [full/evidence/f01.md](full/evidence/f01.md).
Backend baseline: **129 passed, 3 skipped**; эти 3 recovery checks отдельно: **3 passed**.
Новые F01 contract/DB-guard tests: **5 passed**. Playwright: **9 passed**.
Scripted MVP regression evals в Full test DB: **12/12**, hard safety gate true;
это не будущие 50 Full evals. Ruff/format/mypy, Compose config и HTTP smoke прошли.
Fresh Full setup/seed выполнен, все Full сервисы healthy; тестовый проект остановлен без удаления volume.

MVP: 184 file fingerprints (tracked source/media/docs + .env), main/HEAD, четыре image tags,
volume metadata совпали с pre-build baseline. Дополнительный read-only content fingerprint
MVP volume (1343 файла) совпал до/после финальных проверок; он снят после начала Full setup,
что явно отмечено в evidence. MVP не запускался, не мигрировал, не пересобирался;
исходный git status чист. [Isolation report](full/evidence/f01-isolation.json).

Внешние вызовы: только получение build dependencies/images; application calls — локальные
synthetic fixtures/MCP/PostgreSQL. Provider/Prometheus/Jira вызовов не было, paid LLM cost 0.
Blockers F01 отсутствуют. CI workflow адаптирован, remote CI run не выполнялся и не заявляется.
Evidence commit subject: `feat(full): isolate F01 foundation and preserve portfolio MVP`.
Следующий этап F02 остаётся not_started; выполнение остановлено на F01 по запросу владельца.

## F02 — Tenant data и RLS

26 октября 2026. Worktree `C:\Users\user\.codex\worktrees\opspilot-full-f01\AI Incident & Operations Agent`;
ветка `codex/opspilot-full`; base SHA `0d529b0eb3f31619e014e6d1e163a49b5f11e66c`.
Schema `0003_tenant_rls`; SDK checkpoint migration 9; graph blob
`5ea9d96354e37e4b8c54719006e1ac0b836866f1`, policy blob
`7dddb49f221d157d8859295d2e85b28ae05e1824`, public state schema 1.

Реализованы identity foundation, tenant keys всех существующих domain/workflow/checkpoint rows,
9 composite FK, tenant-scoped command keys, FORCE RLS (15 таблиц), transaction-local контекст,
tenant-filtered repositories и защита identity map при смене scope. Runtime роли не владельцы
таблиц, без superuser/BYPASSRLS. Checkpoint schema теперь создаётся административной миграцией;
runtime только проверяет pinned level, DSN/actual database/schema и работает в доверенном tenant scope.
Threads привязаны составным FK к tenant/run; epoch fencing остаётся F06.

Два synthetic tenant имеют одинаковые customer names, но разные customer/integration/ticket IDs.
API/MCP используют только конфигурируемый локальный synthetic scope; MCP client отвергает mismatch,
аргументы и X-Tenant-ID не дают полномочий. Это scaffold F02, не реализация OIDC/публичной авторизации.
Свежая Full-БД и upgrade воспроизводимой fixture-схемы MVP проверены без чтения runtime DB MVP;
неизвестная принадлежность останавливает и откатывает migration. Обновлена также dev БД opspilot_full.

Изменения: `migrations/versions/0003_tenant_rls.py`, `src/opspilot/tenancy/`, identity/domain/workflow
models, DB engine, scoped repositories/API/MCP/CLI/checkpointer, fixtures, тесты и Full scripts/CI.
Контракты/ADR и runbook: [tenancy.md](full/tenancy.md), [ADR 004](full/adr/004-tenant-isolation.md).
Точные команды/версии/отчёты: [F02 evidence](full/evidence/f02/README.md).

Проверки: migration gates **4 passed**; основной backend **164 passed, 7 skipped** (4 migration
и 3 recovery выполнены отдельно); финальные checkpoint guard/SDK **11 passed** — 4 новых и 7 повторных.
Итого 168 различных backend cases, без повторного счёта SDK проверок. Recovery **3 passed**,
Playwright **9 passed**, scripted regression evals **12/12**, hard safety gate true.
Ruff/format/mypy прошли (84 source files); Full UI/API HTTP 200 и real MCP SDK smoke прошли.
После последних DB-guard изменений SDK/guard/lint/types и live smoke перепроверены отдельно.
Тестовые projects остановлены без удаления volumes; отдельный dev Full остаётся запущен.

MVP: 184 fingerprints source/media/docs/.env, main/HEAD, четыре image tags, volume metadata и
read-only content fingerprint 1343 файлов совпали с сохранённым baseline; исходный checkout чист.
[Preservation evidence](full/evidence/f02/mvp-isolation.json). Порты MVP 8000/8081 не изменены;
Full остаётся на 8011/8091, Jaeger 16696. F01 reports сохранены, F02 reports вынесены отдельно.

Внешние application calls: только локальные synthetic MCP/PostgreSQL fixtures; paid LLM/provider,
Prometheus/Jira calls — 0. Remote CI не запускался и не заявляется. Blockers F02 отсутствуют.
Known limits: local synthetic scope до F03/F04; семь Alembic deprecation warnings не влияют на gates.
Evidence commit subject: `feat(full): add F02 tenant isolation and safe fixture upgrades`.
Следующий F03 остаётся not_started; следующие этапы по запросу владельца не начинались.

## F03 — Identity, sessions и роли

26 октября 2026; прежний отдельный Full worktree/ветка codex/opspilot-full, base a65f702.
Schema 0004_identity_sessions; graph/policy версии F02 не менялись, public state schema 1.
Реализованы отдельный pinned Keycloak dev issuer и volume (8181), BFF Authorization Code + PKCE,
one-time state/nonce/browser binding, pinned RS256/JWKS validation, server sessions/fixation prevention,
expiry/logout, live membership checks, CSRF/exact origin, login/tenant UI и роли. Default self-approval
запрещён; local demo O+A exception явно показан и записан в approval вместе с decided_by.
Новый identity gateway role — без ownership/superuser/BYPASSRLS и без domain data permissions.

Пути: auth/, cli/bootstrap_identity.py, migrations/0004, infra/identity/, API/runtime/models,
web/AuthGate и auth-aware client, Full Compose/template/scripts и identity/real browser tests.
[Architecture/runbook](full/identity.md), [точные команды и evidence](full/evidence/f03/README.md).
Проверки: backend 178 passed, 7 dedicated skips; final identity suite 5 passed (1 новый + 4 повтора),
179 различных backend cases. Настоящий OIDC browser 11/11; recovery 3/3; scripted regression evals
12/12, hard safety gate true; Ruff/mypy прошли (90 source files). Live Full schema 0004, UI/API HTTP 200.
MVP fingerprints source/media/.env/main/images/volumes совпали, исходный checkout не менялся.
Тестовые projects остановлены без удаления volumes; dev Full запущен отдельно.
Вызовы — local synthetic issuer/PostgreSQL/MCP; paid provider calls 0. Remote CI не заявляется.
Limits: HTTP dev issuer, BFF-local logout (не IdP-wide SSO logout); публичный pilot не открыт.
F04 authorization/context ещё не реализованы в этом коммите; F05 не начинался. Blockers F03 нет.
Evidence commit subject: feat(full): implement F03 OIDC sessions and tenant roles.

## F04 — сквозная API → execution context → MCP authorization

26 октября 2026; тот же отдельный Full worktree/codex/opspilot-full; base 75367f9.
Schema 0005_authorization_context; service context version 1; graph/policy blobs остаются F02,
public state schema 1. F03 выполнен и закоммичен отдельно до F04.

Full V1 закрыт (410 после auth), UI/API перенесены на V2. Реализованы tenant/actor/role checks
для snapshot/actions/evidence/history/counts, scope-bound cursor, membership admin mutations,
actor-bound client_request_id replay и минимальный health без внутренних данных. Returned snapshot
URL использует V2. Неавторизованный/невыбранный tenant отклоняется до object lookup.

MCP требует отдельный bearer и Ed25519 context с issuer/audience/environment/expiry/kid/scope;
read context не даёт action authority. Write проверяет точный hash/run/action/tool, persisted approval,
current actor/approver membership, self-policy и атомарный receipt. Runtime роли не получают UPDATE
membership: узкий tenant-checked read/lock helper сериализует revoke/write. MCP получает только
public keys, без private signer/BFF secret. Current/next rotation доказана реальным MCP HTTP fixture.
Execution/resume/recovery загружают actor из persisted run, не из approver context. Checkpoint RLS
дополнен actor/thread mapping; отдельные durable jobs и epoch fencing остаются F05/F06.

Пути: migrations/0005, auth/{execution,service_context}, MCP auth/authorization/write, V2 routes,
Core/runtime/recovery/checkpointer, Full secret mounts/keygen/script, UI client и tests.
[Runbook/границы](full/authorization.md), [команды/evidence](full/evidence/f04/README.md).
Проверки: backend 200 passed, 7 dedicated skips; browser 12 passed; recovery 3 passed;
scripted regression 12/12, hard safety gate true. Финальные 17 auth/identity cases повторены после
последних contract/security corrections; Ruff/mypy прошли (95 source files). Это повторы, не новые cases.
Два tenant прошли собственные GreenShop operator→approver→MCP→verified сценарии и не видят чужие
UUID/evidence/counts. Отзыв approver/read-context without authority блокируют запись.
Live dev Full обновлён 0004→0005; HTTP/SDK smoke и runtime-role lock helper проверены.

MVP source/media/.env/main/images/volumes fingerprints совпали; исходный checkout чист и на f9f8d79.
Все прежние F01–F03 reports сохранены. Full dev запущен на 8091/8011/16696/8181; тесты остановлены
без удаления volumes. Внешних paid/model/vendor calls — 0, remote CI не заявляется.
Limits: локальный synthetic issuer; фоновые задачи пока в API; ревизии/TTL/F09, freshness/F12,
SSE/F13, admin UI/F14 и deployment/F23 не выдаются за готовые. Blockers F04 отсутствуют.
Evidence commit subject: feat(full): enforce F04 API and scoped MCP authorization.
Следующий F05 остаётся not_started; диапазон F03–F04 завершён, следующие этапы не начинались.

## F05 — durable command queue и отдельный worker

26 октября 2026; worktree `C:\Users\user\.codex\worktrees\opspilot-full-f01\AI Incident & Operations Agent`;
ветка `codex/opspilot-full`; base SHA `a332965b4d0fcbd2095aaaf9d5c8b3ff3dc77fdc`.
Schema `0006_command_jobs`, initial command definition 1, checkpoint SDK migration 9;
graph `5ea9d96354e37e4b8c54719006e1ac0b836866f1`, policy
`7dddb49f221d157d8859295d2e85b28ae05e1824`, public state/service context version 1.

API атомарно создаёт run+start job и decision/status+resume job. PostgreSQL queue имеет tenant RLS,
composite FK, unique command keys, committed claims, attempts/backoff и dead-letter. Graph invoke/
resume и checkpoint recovery выполняет отдельный worker; API singleton и in-memory scheduler удалены.
Сохраняются начальные budget/model/scenario параметры; execution actor загружается из persisted run.
Один worker удерживает session advisory lock; второй реальный процесс отвергается. SIGTERM завершает
активную команду; SIGKILL оставляет claim для bounded retry после рестарта. Это не F06 fencing.

Пути: migrations/0006, runtime/{jobs,worker,recovery,run_service}, agent/service, API lifespan/health,
CLI/eval harness, Full/legacy-isolated Compose, текущие CI/stage scripts, tests и docs.
[Runbook](full/durable-jobs.md), [точные команды/evidence](full/evidence/f05/README.md).
Backend **205 passed, 6 dedicated skips**; исправленный процессный gate **5 passed**, из них 4 повтора
и 1 новый case: **206 уникальных backend cases**. Три прежних checkpoint recovery cases входят в 205.
Реальный OIDC/browser с отдельным Compose worker **12 passed**; scripted regression **12/12**,
hard safety gate true. Ruff/format/mypy (97 source files), Compose config и live SDK smoke прошли.
Процессный gate доказывает API kill после commit до response для create/decision, replay/offline
worker, SIGKILL после claim, backoff/start attempts=2, singleton и drain активного resume при SIGTERM;
одна фактическая local ticket operation и exact verification. Rollback, tenant deny, dead-letter и
saved-budget tests прошли. Timing race тестового kill исправлен и проверен повторным process gate.

Dev Full мигрирован 0005→0006, отдельный worker запущен; UI 8091/API 8011 HTTP 200, MCP SDK 9 tools.
Тестовый project остановлен без удаления volumes. MVP: 184 source/media/docs/.env fingerprints,
main/HEAD, четыре image tags, volume metadata и read-only content SHA256 совпали с baseline до/после;
исходный checkout чист. [Preservation evidence](full/evidence/f05/mvp-isolation.json).
Внешние application calls — только локальные synthetic OIDC/PostgreSQL/MCP; paid/provider/vendor
calls 0. Remote CI не запускался и не заявляется. F01–F04 evidence сохранены.

Limits: один worker; epochs/leases/stale-writer fencing — F06, events/outbox — F07. Interrupted graph
без безопасного checkpoint завершается conservative failure; автоматический blind write retry
не добавлен. Blockers F05 отсутствуют. Evidence commit subject:
`feat(full): implement F05 durable jobs and independent worker`.
Следующий F06 остаётся not_started; работа завершена только на F05 по запросу владельца.

## F06 — multiworker, leases и fenced checkpoints

26–27 октября 2026; финальные gates 27 октября. Worktree
`C:\Users\user\.codex\worktrees\opspilot-full-f01\AI Incident & Operations Agent`,
ветка `codex/opspilot-full`; base `0f705a00fa90d342178094f50920f8fa5e60a7fe`.
Schema `0007_execution_fences`; runtime workflow `full-graph-v1`, public state/service context 1,
checkpoint SDK migration 9. Graph `5ea9d96354e37e4b8c54719006e1ac0b836866f1` и policy
`7dddb49f221d157d8859295d2e85b28ae05e1824` не менялись.

Вместо process singleton — tenant/run ownership row, монотонный epoch, heartbeat и reaper по времени
БД. Claims и ack привязаны к owner/epoch; отменённая без ack job сохраняется для expiry/backoff,
после пяти transient failures — dead-letter/needs_attention. Два отдельных Compose workers.
DB triggers fence фактические workflow projections, actions/worker approvals, local effects/receipts,
checkpoint/blobs/pending writes. SDK adapter сохраняет blob+checkpoint и batch pending writes в одной
короткой транзакции с ownership row lock; bound context не обновляется старому callback.
MCP получает owner/epoch в signed action context и независимо проверяет их в транзакции local write.
Перед read/model dispatch также проверяется live fence. Heartbeat проверяет expiry после получения
row lock; runtime DB statement/idle-in-transaction timeout 5s не даёт SIGSTOP бесконечно держать lock.
Pinned workflow/schema и corrupt run/thread/mode checkpoint останавливают dispatch в needs_attention.

Пути: migrations/0007; runtime/{fencing,jobs,worker,recovery,run_service}; checkpoint adapter,
DB engine/models, auth context/MCP local write, runtime dispatch, Full Compose/CI/setup, tests/docs.
[Контракт/runbook](full/execution-fencing.md), [ADR](full/adr/006-fenced-checkpoint-adapter.md),
[команды и measured evidence](full/evidence/f06/README.md).
Backend **211 passed, 9 dedicated skips**, SDK rollback/heartbeat/epoch reuse/corrupt-binding gates
включены. Queue process suite **5 passed** (4 повтора + 1 новый); multiworker fault suite **3 passed**:
всего **215 уникальных backend cases**. Реальный OIDC/browser с двумя workers — **12 passed**;
scripted regression **12/12**, hard safety gate true. Ruff/format/mypy (98 source files) прошли.
Нормальные проверки используют production 30s/10s; fault subprocesses явно переключаются на 3s/1s.
SIGKILL, SIGSTOP внутри SDK transaction и настоящий TCP partition завершены одним verified ticket;
после takeover старый epoch отвергнут на всех восьми границах. Старый owner UUID с новым epoch
проверен отдельно; старый epoch не получает authority. Process fixture SIGTERM readiness race
устранена и затронутые gates повторены; предыдущие красные прогоны не объявляются зелёными.

Свежая test DB до 0007 и отдельный dev Full upgrade 0006→0007 выполнены без экспорта MVP.
Dev Full: два workers, UI 8091/API 8011 HTTP 200 и scoped real MCP SDK smoke; test project остановлен
без удаления volumes. MVP 184 fingerprints source/media/docs/.env, main/HEAD, четыре image tags,
volume metadata/content SHA256 совпали до/после и после возобновления; исходный checkout чист.
[Preservation](full/evidence/f06/mvp-isolation.json), [live](full/evidence/f06/live.json).
Docker startup после паузы восстановлен сохранением stale runtime socket directory, без reset/удаления
volumes. F01–F05 reports сохранены; внешние application calls только local synthetic OIDC/PG/MCP,
paid/provider/vendor calls 0. Remote CI не запускался и не заявляется.

Blockers F06 отсутствуют. Transactional events/audit/outbox, полный UI, usage/load/holdout/pilot gates
остаются своими этапами. Evidence commit subject:
`feat(full): implement F06 multiworker leases and fenced checkpoints`.
Следующий F07 остаётся not_started; выполнен только F06 по запросу владельца.


## F07 — transactional events, audit и projections

27 октября 2026. Canonical worktree
`C:\Users\user\.codex\worktrees\opspilot-full-f01\AI Incident & Operations Agent`,
ветка `codex/opspilot-full`; base `829670ffefe4f45c3be14efcd2ec599c0bb6e4af`.
Schema `0008_transactional_events`, workflow `full-graph-v1`, DTO/event schema 1.

Tenant-scoped FORCE-RLS run_events/run_audit/outbox записываются DB triggers в той же
транзакции, что run/approval/operation receipt; rollback не оставляет orphan events.
Per-run row lock выделяет monotonic sequence; bounded payload содержит только публичные
статусы/идентификаторы/reason codes. Audit связывает actor/service, action, epoch и redacted
diff с event UUID/run/sequence. Runtime роли не могут изменять event/audit storage напрямую.
Fenced recovery имеет собственное persisted event. Membership mutation и security audit
теперь также transactional. Старые runs получают явно обозначенный baseline.

Worker публикует bounded outbox batches; PostgreSQL wakeups содержат только identifiers,
DB replay авторитетен. Duplicate/out-of-order delivery не меняет state и не уменьшает watermark.
Persisted events/audit API проверяет object authorization перед replay, имеет подписанные
actor/tenant/run/stream cursors, страницы до 100 и окно 1000 sequences с snapshot reset.
Snapshot восстанавливается из committed source projection и authoritative run/approval/receipt
под repeatable read; public DTO использует вложенный allowlist, private graph state не экспортируется.
SSE остаётся F13, retention/archival — F17; F08 не начинался.

Пути: migration 0008; API routes/health; runtime events/recovery/worker/snapshots;
public contracts/web types; tests, Full test Compose/CI/scripts и docs.
[Контракт и measured evidence](full/evidence/f07/README.md),
[checks](full/evidence/f07/checks.json), [live](full/evidence/f07/live.json).
Release entry point: `scripts/test-full-f07.ps1`; project `opspilot-full-test-f07`,
DB `opspilot_full_test`, test ports отсутствуют. Backend **222 passed, 9 skipped**, включая
11 F07 DB/API/fault cases; queue suite **5 passed** (4 повтора), multiworker faults **3 passed**;
всего **226 уникальных backend cases**. Browser/OIDC с двумя workers **12/12**;
scripted evals **12/12**, hard safety gate true; Ruff/format/mypy (100 source files) прошли.
Проверены crash до/после commit/publication, rollback, concurrent sequence allocation,
duplicate/out-of-order delivery, snapshot cache loss, immutable audit, private-state redaction,
RLS/cursor scope, bounded reset и stale epoch. SIGKILL/SIGSTOP/TCP partition F06 не регрессировали.

Исправлены найденные DTO/test assumptions; полный backend повторён. Два browser timeout при
одновременных dev/test стеках исчезли после остановки только dev Full; весь browser suite повторён
успешно, timeout/логика исполнения не ослаблялись. Fresh schema install и dev Full upgrade 0007→0008
выполнены. Dev Full восстановлен с двумя workers; UI/API HTTP 200, MCP protocol 2025-11-25/9 tools,
новый synthetic diagnosis run завершён с event/audit и опубликованным outbox. Test stack остановлен
без удаления volumes. MVP 184 fingerprints, main/HEAD, четыре image tags, volume metadata/content
совпадают до/после; исходный checkout чист. [Preservation](full/evidence/f07/mvp-isolation.json).
Paid/provider/vendor calls 0; remote CI не запускался. Blockers F07 отсутствуют.
Отдельный локальный commit subject: `feat(full): implement F07 transactional events audit and projections`.
Следующий этап F08 остаётся not_started.


## F08 — durable clarification и cancellation

27 октября 2026. Канонический worktree
`C:\Users\user\.codex\worktrees\opspilot-full-f01\AI Incident & Operations Agent`,
ветка `codex/opspilot-full`; base F07 `bd2350178597f6dff191d5d1e206a49841a503c8`.
Schema `0009_human_commands`, workflow `full-graph-v1`, state/DTO/event schema 1,
checkpoint SDK migration 9. Graph blob `d2091b610b027f295629ea7163e6353a3b4bac41`,
policy blob `7dddb49f221d157d8859295d2e85b28ae05e1824`.

Добавлены typed customer/integration/timezone forms, стабильные IDs, TTL 24 h с настройкой
CLARIFICATION_TTL_SECONDS, два раунда и pure checkpointed interrupt. Answer + tenant-RLS
immutable command ledger + resume job + event/audit/outbox атомарны. DB-time acceptance,
stale/forged/opposite conflict, replay между раундами и восстановление следующей формы
после checkpoint/projection gap проверены. Принятый вовремя ответ переживает задержку очереди;
expiry sweep ограничен 100 runs. API разрешает команды только operator-владельцу run.

Cancel + durable command атомарны; состояния waiting_for_input→queued и cancelling→cancelled.
Проверки выполняются перед node/model/read/write dispatch; MCP повторяет проверку в локальной
транзакции. Cancel/local write сериализуются ownership-row lock. Report строится по committed
receipts, сохраняет выполненные/unknown effects и перечисляет отменённые undispatched actions.
Известная отмена до dispatch не превращается transport task group в unknown write.
Cancellation guards переиспользуют worker DB engine. Совместимость F07 approval interrupts
сохранена; full UI остаётся F14, revisions/approval TTL/grants — F09.

Пути: migration 0009, agent nodes/state/graph/service/runtime, runtime human_commands,
run_service/recovery/worker/fencing, API/public DTO, MCP ticket service, Full Compose/env example,
client types, tests, stage/live scripts и docs. [Контракт](full/human-commands.md),
[команды/evidence](full/evidence/f08/README.md), [checks](full/evidence/f08/checks.json).
Project `opspilot-full-test-f08-release`, DB `opspilot_full_test`, test ports отсутствуют.
Backend **239 passed, 9 skipped**, включая **18 F08 cases**; queue suite **5 passed**
(четыре повтора), multiworker faults **3 passed**: **243 уникальных backend cases**.
Browser/OIDC с двумя workers **12/12**, scripted evals **12/12**, hard safety gate true.
Ruff/format/mypy (102 source files), TypeScript/Vite и Compose config прошли.

Проверены ambiguous Green RU/EN, timezone/DST, новый процесс с pending interrupt, restart
после answer commit, forged/stale/opposite/duplicate answers, два раунда и expiry, rollback,
foreign owner/role/tenant denies, cancel queued/running/waiting, отсутствие tool call после
pre-dispatch cancel, cancel во время открытой write transaction и после committed response.
Найденные projection/transport ошибки исправлены; история красных кандидатов и transient
ускоренных fault failures честно сохранена в evidence, deadlines/assertions не ослаблены.

Dev Full upgrade 0008→0009 выполнен; финальный live run прошёл clarification→approval→cancel,
MCP 9 tools, event/audit/outbox согласованы; два workers healthy, UI/API HTTP 200.
[Live](full/evidence/f08/live.json). Все test stacks остановлены без удаления volumes.
MVP 184 fingerprints source/media/docs/.env, main/HEAD, четыре image tags, volume metadata
и read-only content hash совпали до/после; исходный checkout чист.
[Preservation](full/evidence/f08/mvp-isolation.json). F01–F07 evidence сохранены.
Application calls только local synthetic OIDC/PostgreSQL/MCP; paid/provider/vendor calls 0,
remote CI не запускался. Blockers F08 отсутствуют.
Отдельный локальный commit subject: `feat(full): implement F08 durable clarification and cancellation`.
Следующий этап F09 остаётся not_started; выполнен только F08 по запросу владельца.

## 27 октября 2026 — security-задачи в плане реализации

После baseline `48486d0` по запросу владельца ASVS 5.0.0 L2 включён в обязательства F09–F24.
Добавлены пакеты SEC-01–12, предварительные contracts и security gates в спецификации,
security-колонка этой очереди и backlog 253 requirement-specific tasks с accountable stage.
Scope-changing этап повторно проверяет затронутые controls, даже если primary owner — другой этап.
N/A — отдельная задача проверки применимости, не требование реализовать отсутствующую функцию.

Проверены JSON/уникальность и полнота 253 IDs, неизменность исходных levels/assessments,
валидность SEC/F owners, наличие security gates у всех F09–F24, локальные Markdown links,
сохранение 24 stage statuses и `git diff --check`. Source hashes security baseline совпадают.
Application/DB/Compose/CI/deployment не менялись; новые runtime тесты не требуются для этой
документационной задачи и не заявляются. MVP checkout не изменялся.
F09 остаётся следующим `not_started`; весь L2 по-прежнему NOT_MET.
Отдельный local commit subject: `docs(full): integrate ASVS L2 security tasks into implementation stages`.


## F09 — action revisions, approval и grants (27 октября 2026)

Статус: done. Scope сохраняется: один исполняемый create_ticket,
без новых tools F10 и DAG F11. Logical intent и immutable revisions отделены migration 0011;
strict expected_version, DB-time approval TTL, supersede/revoke/expiry и durable resume.
Core выдаёт transient Ed25519 grant с независимым purpose/key generation ID, jti, epoch,
exact revision hash и lifetime ≤60 секунд/остатка approval. MCP повторно проверяет persisted
approval, актуальные роли/ownership/self-approval/tenant/fence; consume + ticket + receipt атомарны.
API не имеет private grant keys. В public DTO/model/checkpoint/audit JWT не передаётся.

До migration записаны [security contracts](full/f09-security-contracts.md). SEC-01/02/03/04/05/06
проверяются в локальном scope; SEC-10 дополняет change gate scan/audit и remediation policy.
Первый runtime scan обнаружил CVE: runtime переведён на поддерживаемый Alpine с vendor updates,
uv исправлен, неиспользуемый системный pip с vendored vulnerabilities удалён. Это исправления
Full; исходный MVP не менялся. Поздние requirements менеджера/retention/collector/IdP/deployment
остаются конкретными задачами F17/F16/F23/F24; полный ASVS L2 по-прежнему NOT_MET.

Измеренная приемка и границы: [F09 evidence](full/evidence/f09/README.md).


F09 acceptance: Python 301 passed / 9 skipped; browser 12; durable queue process 5;
fencing kill/stop/partition 3; scripted evals 12/12 с 0 unauthorized/duplicate writes.
Ruff/format/mypy, real local TLS/MFA (8+11 checks), legacy upgrade (2 receipts preserved),
SCA app/web 0 findings, Python/npm audit 0, live key separation/DB audit privileges — pass.
MVP fingerprint сохранён. Отдельный локальный commit F09; push не выполнялся.
Следующий этап — F10, он остаётся not_started.


## F10 — local ticket/comment/internal inbox operations

28 октября 2026. Canonical Full worktree
`C:\Users\user\.codex\worktrees\opspilot-full-f01\AI Incident & Operations Agent`,
ветка `codex/opspilot-full`; base F09 `278d92d`. Schema `0012_local_operations`;
workflow `full-graph-v1`, state/DTO/revision schema1, checkpoint SDK migration9.

Добавлены add_ticket_comment/notify_manager и get_ticket_comment/get_notification.
Immutable revision и независимый signed grant привязаны к конкретному tool и всем утверждённым
полям. MCP перепроверяет tenant/actor/approval/roles/TTL/fence/cancellation; existing ticket/customer
и доступ к target, enabled tenant recipient. Domain row + grant consume + receipt атомарны;
concurrent replay возвращает тот же объект. DB trigger блокирует target без выдачи runtime UPDATE.
Independent verification сравнивает approved fields, generated ID/time и origin operation;
missing/mismatch не дают verified success, lost response восстанавливается из receipt.

SEC-01/03/06/08/10: [security contracts](full/f10-security-contracts.md), классификация новых
body/recipient fields, FORCE RLS, private reads, operation-specific DTO и React text rendering,
ASVS scoped contributions без полного закрытия норм. Полный L2 NOT_MET; retention/managed storage,
operational controls и deployment остаются F17/F23/F24. F11 DAG и F14 full inbox UI не начинались.

[Measured acceptance и команды](full/evidence/f10/README.md): backend **331 passed / 9 dedicated
skips**, включая все26 F10 PostgreSQL/MCP cases; browser/OIDC **12/12**, durable queue process **5**,
fencing kill/stop/partition **3**, scripted evals **12/12**, hard safety gate true, unauthorized/
duplicate/false verified writes0. Ruff/format/mypy111, TypeScript/Vite, real Chromium new-field
XSS/text check, fresh TLS/MFA **8+11** проходят. Runtime SCA HIGH/CRITICAL0, Python/npm audit0.

Исходные Docker500/DNS blockers сняты после разрешённого владельцем restart (при зависшем stopping
завершён только docker-desktop WSL). Сохранены failed candidates: readiness pin0011→0012 и
неверный FOR UPDATE на tickets исправлены; privileges/assertions/deadlines не ослаблены.
Fresh synthetic TLS profile использует новые credentials; секреты не включены в artifacts.

Dev Full upgrade0011→0012 сохранил все прежние tickets/receipts; два worker healthy,
UI8091/API8011 HTTP200, real MCP13 tools и новый read-only queued run завершён с event/audit.
MVP184 source/media/docs/env fingerprints, main/HEAD, images, volume metadata/content совпали
после restart и после финального rollout; исходный checkout чист. Test containers/networks
удалены без удаления volumes/images. [Preservation](full/evidence/f10/mvp-isolation.json).
Application calls только локальные synthetic OIDC/PG/MCP; paid/vendor writes0. Dependency/image
scanner downloads были; remote CI, real provider и production deployment не запускались.
Blockers F10 отсутствуют. Локальный stage commit subject:
`feat(full-f10): implement local ticket comment and internal inbox operations`.
Следующий F11 остаётся not_started; выполнен только F10.


## F11 — mixed plans, dependencies и approval waves

28 октября 2026. Canonical Full worktree/ветка `codex/opspilot-full` сохранены;
base F10 `efc6f1b`. Schema `0013_mixed_plans`; mixed requests закреплены за
`full-graph-v2`, прежние v1/checkpoints и single-action path поддерживаются.
State/DTO/revision schema1, checkpoint SDK migration9 не переинтерпретируются.

Реализованы typed bounded DAG (до3 actions/2 waves), immutable per-run plan и stable business
intent slots. У каждой concrete action своя revision/decision/grant; Core и MCP независимо
проверяют plan membership, завершённость решений wave и verified dependency receipts.
Approved subset исполняется последовательно, rejected/unknown prerequisites дают skipped
 dependents. Comment materializes только после verified ticket, получает новый exact ticket ID
и отдельную approval card/decision wave. Replay plan переиспользует intents; изменение plan
не повторяет succeeded effects. Per-action verification резерв до3 чтений хранится в БД.
Durable resume successor закрывает race второй wave с ack текущей job.
API/UI показывают каждую decision/execution/verification; partial plan не выдаётся за global success.

SEC-01/03/07/10: [contracts](full/f11-security-contracts.md), scoped contributions в ASVS backlog;
все253 IDs/levels/baseline assessments сохранены, whole-norm closure не заявляется, L2 NOT_MET.
[Evidence](full/evidence/f11/README.md): backend **351 passed/9 dedicated skips**, дополнительные
mixed cancellation **2 passed** на том же application image; focused8 входят в backend.
Browser/OIDC **14/14**, queue process **5**, fencing kill/stop/partition **3**, TLS/MFA **8+11**,
scripted evals **12/12**, unauthorized/duplicate/false verified writes0. Ruff/format/mypy115,
TypeScript/Vite, runtime app/web SCA0, Python/npm audit0 проходят.
Реальный child-worker crash между actions и гонка next-wave decision/ack проверены.

Исправлены и сохранены красные кандидаты: unfenced updated_at на partial decision,
pytest module collision, SQL NULL vs JSON null в legacy binding. Fresh verified project
`opspilot-full-test-f11-verified`, DB `opspilot_full_test`, published ports отсутствуют.
Runtime115 source files совпадают с проверенным image; evals честно отмечают dirty snapshot.

Dev Full upgrade012→013 сохранил counts и SHA-256 прежних domain objects/actions/receipts.
Live v1 read-only и v2 mixed run с2 approval waves/3 verified receipts прошли; replay вернул
тот же run. MCP13 tools, UI8091/API8011 HTTP200, два workers healthy.
MVP184 source/media/docs/env fingerprints, main/HEAD, image tags и volume metadata/content
совпали с baseline; исходный checkout чист. Test/lab containers/networks удалены, volumes/images
сохранены. Application calls только local synthetic OIDC/PostgreSQL/MCP; paid/vendor writes0.
Remote CI, real provider и production deployment не выполнялись. F12 не начинался.
Blockers F11 отсутствуют. Отдельный local commit subject:
`feat(full-f11): implement bounded mixed plans and approval waves`.


## F12 — freshness, expiry, revocation и bounded replan

29 октября 2026. Base F11 `4d70288`; canonical Full worktree/ветка сохранены.
Schema `0014_freshness`, прежние pinned v1/v2 graphs/checkpoints поддерживаются.
Core и MCP независимо читают uncached local preconditions; configuration/target rows share-locked
в effect transaction. Healthy/unknown/timeout не разрешают запись. Возраст monitoring≤5min по DB time; stale/future source timestamps запрещены. Freshness snapshot входит
в immutable revision digest; публично только bounded status/IDs/role eligibility и fingerprints.

Material drift supersedes старое неисполненное согласие, отзывает grants и требует отдельного
approval новой revision. Один replan/run, максимум2 approval rounds: DAG уже с2 waves при drift
останавливает изменившееся действие без третьей wave. Completed/uncertain intents не меняются, succeeded siblings
сохраняются. DB-time scheduler/TTL/revoke/roles и grant key current/next overlap проверены;
terminal run не разрешает новые effects. Verification quota3/action отдельно от research,
персистентна, tenant FORCE RLS и fenced. Реальная авария worker после replan commit до checkpoint
восстанавливает ожидание нового согласия. API/UI показывают точную новую revision/preconditions.

[Contracts](full/f12-security-contracts.md), [evidence](full/evidence/f12/README.md): backend368/9
 dedicated skips, OIDC/browser15, queue5, fencing3, TLS/MFA8+11, eval12/12, unauthorized/duplicate/
false verified0. Ruff/format/mypy117, TypeScript/Vite, runtime HIGH/CRITICAL SCA0 и package audits0.
Исходные F10 negative assertions сохранены; red candidates и исправления отражены в evidence.

Full013→014 сохранил counts/SHA256 domain objects/actions/receipts. Live v1/v2:2 waves/3 receipts,
MCP13, request replay без новых effects; UI8091/API8011 HTTP200,2 workers healthy.
MVP184 fingerprints/main/HEAD/images/volume metadata+content неизменны; исходный checkout чист.
F12 test/lab containers/networks удалены, volumes/images сохранены. Paid/vendor writes, remote CI,
production deployment и push0. SEC-02/03/04 и SEC-01/10 scoped gates проходят; все253 ASVS
IDs/levels/baseline assessments/owners сохранены, full L2 NOT_MET. Только F12 выполнен; F13 не начат.
Blockers отсутствуют. Отдельный local commit subject:
`feat(full-f12): enforce freshness and bounded reapproval`.


## F13 — authenticated SSE replay/reconnect и авторизация

29 октября 2026. Canonical Full worktree
`C:\Users\user\.codex\worktrees\opspilot-full-f01\AI Incident & Operations Agent`,
ветка `codex/opspilot-full`; base F12 `abfaf76`. Schema `0014_freshness`, pinned v1/v2 graphs,
state/DTO1 и checkpoint SDK9 сохранены; migrations нет. Новый cursor protocol v1.
Graph blob `05efb29565b989d831ced8bc2acdc11750b88efb`, policy blob
`d7c0a37ffd28b02b344ce88a6c0639d4bf94b315` не менялись относительно F12.

SSE выбирается `Accept: text/event-stream`; прежний bounded JSON replay F07 сохранён.
Согласованные snapshot_version/latest_event_id и DB replay закрывают snapshot→subscribe gap;
compaction/gaps дают reset/snapshot recovery. MAC cursor привязан к session/actor/tenant/run,
передаётся в Last-Event-ID, URL secrets не создаются. Session/expiry/disable/membership/owner/roles
перепроверяются без cache. Shared DB reservations8/4/2 (global/tenant/actor), batch64, replay lag256,
frame16KiB, lease health1s и send deadline3s; потеря физического reservation закрывает поток.
Клиент дедуплицирует sequences, использует один serial snapshot reader, bounded polling5–10s,
сохраняет terminal/not-found UX и очищает private DOM при потере доступа.

[Contracts](full/f13-security-contracts.md), [evidence](full/evidence/f13/README.md),
[checks](full/evidence/f13/checks.json): backend382/9 dedicated skips, focused25 (subset), host unit129
(subset), real OIDC/Chromium17, queue5, fencing3, TLS8+MFA/browser13, scripted eval12/12,
unauthorized/duplicate/false verified writes0. IdP disable закрыл живой TLS SSE за886ms без polling
/auth/me. Ruff/format/mypy119, TypeScript/Vite, runtime HIGH/CRITICAL SCA0, Python/npm audits0.
SEC-02/07/08 и общие SEC-01/10 gates проходят; все253 ASVS IDs/levels/baseline assessments/owners
сохранены, whole-norm closure не заявляется; полный L2 NOT_MET.

Full rollout сохранил counts/SHA256 прежних domain objects/actions/receipts и schema0014.
Live real OIDC read-only run завершился diagnosis_only; header cursor, SSE reconnect после реального
restart Full API и logout/private DOM reset проверены. UI8091/API8011 HTTP200,2 workers healthy.
MVP184 fingerprints/source/env/main/HEAD/images/volume metadata+content совпали с baseline;
исходный checkout чист. F13 test/lab containers/networks удалены, volumes/images сохранены.

Два Docker Engine500 прервали инфраструктурные candidates; restart был явно разрешён владельцем.
Stale Docker runtime socket сохранён в резервной папке; engine восстановлен. E2E runner получил
private IPC и memory bounds. Исправлены collection name collision, F07 JSON/SSE negotiation,
составная send/revoke граница и лишние/параллельные browser snapshot reads; прежние assertions
не ослаблены. Failed/interrupted candidates сохранены в evidence. Application traffic — только
local synthetic OIDC/PostgreSQL/MCP; dependency/scanner downloads были. Paid/vendor writes,
remote CI, production deployment и push0. Blockers F13 отсутствуют. Только F13 выполнен;
F14 не начинался. Local stage commit subject:
`feat(full-f13): add authorized bounded SSE replay and reconnect`.


## F14 — полный пользовательский workspace и администрирование

29–30 октября 2026. Full worktree/ветка сохранены; base F13 `2fe6613`.
Migration `0014_freshness` → `0015_workspace`: FORCE-RLS inbox read markers, immutable UI commands,
connector controls и narrowly granted fixed-search-path functions. History/cursor filters,
clarification, Cancel/refresh, mixed decisions/revisions/revoke/TTL, unknown/partial reconciliation,
recipient inbox, role-scoped memberships/session/account controls, connector CAS, redacted audit
и bounded metadata exports доступны из браузера. Mode/source/actor/точная revision показаны;
технические grants и credentials в продуктовые формы не вынесены.

[Contracts](full/f14-security-contracts.md), [evidence](full/evidence/f14/README.md),
[checks](full/evidence/f14/checks.json): backend387/9 dedicated skips, browser21, queue5, fencing3,
native TLS8+MFA/browser14, отдельные IdP policy4, scripted eval12/12. Unauthorized/duplicate/
false verified writes0; IdP disable закрыл TLS SSE за605ms. Ruff/format/mypy120, TypeScript/Vite,
PowerShell parsers проходят. Source/image proof:120 Python,35 UI files и3 served assets.

IdP обновлён до pinned Keycloak26.8.1 с security-fixed Java21, checksum-pinned Guava33.7.2,
проверенным default truststore и парольным blocklist/history/length policy. App/web raw H/C0,
package audits0. IdP raw4 HIGH сохранены: точный digest/слои/ELF libuuid и отсутствие затронутого
libmount/nsenter подтверждают неприменимость этих source-package находок. Applicable H/C0;
ignore, удаление metadata и risk acceptance не использованы. Все253 ASVS IDs/levels/baseline/
owners/NA fields сохранены;174 scoped gates прошли,103 primary whole-norm reviews остаются
открытыми. Production recovery/mail/factor-change notifications/admin MFA остаются F23 gates;
full ASVS L2 NOT_MET.

После прерывания миграция уже была committed в БД; повторно не выполнялась. Counts/SHA256
прежних tickets/comments/notifications/actions/receipts совпали с committed F13 snapshot.
Quiesced private IdP backup сохранён под ignored `.tools`, архив проверен. Обновлены только
reviewed realm policy keys; live OIDC smoke подтвердил clarification/cancel/history/export/inbox,
admin connector disable/enable с восстановлением и отдельный auditor view, без ручного admin SQL.
UI8091/API8011 HTTP200;2 workers запущены, runtime image IDs совпали с прошедшими scan images.
MVP184 source/env fingerprints/main/HEAD/images/volume metadata+content неизменны; checkout чист.

Docker Engine/IPC failures прерывали инфраструктурные candidates; Desktop restart был разрешён
владельцем, stale IPC сохранён отдельно без reset/data/volume удаления. В custom IdP исправлены
heap bounds и явный container bind, затем повторены все21 browser и native TLS/MFA gates.
Failed/interrupted candidates сохранены, assertions не ослаблялись. F14 test/lab containers и
networks удалены; volumes/images сохранены. Paid/vendor writes, remote CI, production deploy,
push0. F15 не начат. Blockers F14 отсутствуют. Отдельный local commit subject:
`feat(full-f14): complete scoped operations workspace and administration`.


## F15 — cache, admission, quotas и стоимость

30 октября 2026. Full worktree/ветка сохранены; base F14 `be246d7`.
Migration `0015_workspace` → `0016_governance`: protected PostgreSQL resource policy,
FORCE-RLS reservations/provider attempts, immutable price snapshots, actor quotas across tenants,
fair bounded worker admission, source limits and transactional per-object cache versions.
Separate private ACL Redis uses independent HMAC keys, scoped cache/invalidation, TTL and bounded
fallback; credentials/consent/preconditions/writes/verification are excluded. Research15 и отдельные
verification3/action; retry, timeout/unknown и process crash не возвращают резервы. UI показывает
cached tokens, known subtotal, held tokens/spend и null/partial total без фиктивного zero cost.

[Contracts](full/f15-security-contracts.md), [evidence](full/evidence/f15/README.md),
[checks](full/evidence/f15/checks.json): backend402/11 dedicated skips, browser22, queue5, fencing3,
provider crash1, real Redis stop/recreate1, native TLS8+Redis6+MFA14+IdP policy4, scripted eval12/12.
Unauthorized/duplicate/false verified writes0. IdP disable закрыл TLS SSE за344ms.
Ruff/format/mypy123, TypeScript/Vite и parsers проходят; source/image proof123 Python,36 UI files,
3 served assets. App/web/Redis raw H/C0; Python/npm audits0. Unchanged IdP raw4 HIGH сохранены с
повторно проверенным exact-image/component applicable0 proof; ignore/risk acceptance нет.
253 ASVS protected IDs/levels/baseline/owners/NA fields сохранены;125 scoped reviews проходят,
1 primary contribution оставляет whole-norm verification открытой. Full L2 NOT_MET.

Local Full migration сохранила counts/SHA256 всех12 прежних domain/workflow tables до запуска
workers. Live real OIDC scripted status run завершён diagnosis_only; durable usage и honest zero
API cost пережили browser refresh. UI8091/API8011 HTTP200,2 workers и private Redis запущены;
runtime image IDs совпадают с прошедшими scans. MVP184 source/env fingerprints/main/HEAD/images/
volume metadata+content неизменны, исходный checkout чист. Test/lab containers/networks удалены,
volumes/images сохранены. Docker Desktop/WSL update рекомендован после проверки официальных
версий; host upgrade не устанавливался, точная причина Engine/IPC сбоев не доказана.

Failed/interrupted candidates сохранены отдельно. Исправлены numeric cast, SQL bind JSON,
Windows secret line endings, active-only admission и per-object cache invalidation concurrency.
Hardened unit fixtures изолированы от integration Redis settings; три TLS startup negatives
добавлены. Browser startup отделён read-only ожиданием обработки backend fixture jobs; прежние
assertions/timeouts сохранены. Paid/vendor writes, remote CI, production deploy и push0.
F16 не начат. Blockers F15 отсутствуют. Отдельный local commit subject:
`feat(full-f15): add durable admission budgets and scoped Redis caching`.


## Подготовка рабочего checkout Ops — без начала F16

30 октября 2026. По запросу владельца подготовлена самостоятельная копия Full в
C:\Users\user\Desktop\code\Ops на ветке codex/opspilot-full из F15 4733998.
Git objects скопированы без hardlinks/alternates; исходные MVP и Full checkout сохранены.
Ignored locator MVP теперь указывает на Ops. Локальные env/ключи/Redis secrets/baselines и
последний TLS lab перенесены без ротации; отдельные Python/web зависимости созданы по locks.
F15 runner принимает явный -MvpPath и читает local locator для independent checkout.

[Инструкция](../START-HERE.md), [проверки](ops-workspace-checks.json). Bind mounts действующего
opspilot-full переподключены к Ops. Schema0016, counts/SHA256 12 таблиц и runtime image IDs
сохранены; миграции/seed не запускались. UI/API HTTP200, два workers healthy. Real OIDC,
scripted status run и refresh с прежними usage counters прошли. Source/image proof123 Python
и36 UI files, TypeScript и PowerShell parsers, Git integrity и MVP isolation проходят.
Секреты остаются ignored; paid calls/vendor writes/push0. F16 и будущие этапы не начаты;
full ASVS L2 NOT_MET. Локальный служебный commit subject:
chore(workspace): prepare independent Ops continuation checkout.

## F16 — observability и operator diagnostics

Статус: done. База a06d1a7 (F15 4733998), независимый Ops checkout; MVP сохранён.
[Результаты](full/evidence/f16/checks.json), [SEC-05 contracts](full/f16-security-contracts.md),
[runbook](full/f16-observability-runbook.md), [evidence](full/evidence/f16/README.md).

API/job/worker epoch, graph, LLM, signed MCP, adapters, verification и reconciliation связаны
trace IDs/parent links. Команды хранят traceparent и initial/claim timestamps в0017_observability.
Два отдельных worker processes подтверждают новый epoch/trace при продолжении и завершённый
span/освобождённый lease на human pause. SSE tracing завершается на headers; idle worker/SSE
SQL polling не создаёт root traces, активные SQL/error spans и database-failure diagnostics сохранены.

Collector: native mTLS + role tokens, private port, source/ingress positive schema, bounded
queues/requests/storage/retention, non-root/read-only/caps-drop, metadata HMAC chain и отдельный
sealed head. Verify/read/append используют защищённые SQLite snapshots/transactions.
Реальные outage/tamper/paired recovery и sentinel probes прошли; private forensic copies сохранены.
Nginx error/access diagnostics продолжают работать и не выводят secret/URI/header/body.
Dashboard проверяет live role/tenant/actor через SQL и показывает scoped queue/lease/wait/active/
budget/unknown/error metadata и проверенные alert conditions; это project thresholds, не SLO/paging.

Frozen backend422/11 dedicated skips; targeted21; HTTP/journal units38; browser23;
queue5, fencing3, provider crash1, Redis stop/recreate1; native TLS8 +collector12 +Redis6 +
MFA14 +IdP policy4; scripted eval12/12, hard safety true, unauthorized/duplicate/false success0.
Ruff/format/mypy131, TypeScript/Vite и PowerShell parsers проходят; source/image131 Python
и38 UI/browser files совпадают. Runtime app/web/Redis raw HIGH/CRITICAL0, Python/npm0;
IdP raw4, applicable0 по fresh exact-image assessment, без ignore/removal/risk acceptance.

Dev Full обновлён0016→0017; counts/SHA legacy projections всех12 таблиц совпали до запуска
workers; только три новые command columns исключены из legacy projection. Реальные OIDC,
scripted worker, refresh, diagnostics и readiness прошли. Live images совпадают со scans.
MVP184 files/env, branch/HEAD, images и volume metadata/content совпали с baseline.
ASVS253 inherited fields/owners/N/A сохранены:141 scoped и16 primary contributions, без
whole-requirement closure; полный L2 NOT_MET. Production anchors/PKI/secrets/clock/retention/
paging/load остаются открытыми operational gates. Paid calls/vendor writes/push0; F17 не начат.
Отдельный local commit subject: feat(full-f16): add protected telemetry and scoped operator diagnostics.


### F17 — lifecycle, secrets и локальный Full Core

6 ноября 2026; `C:/Users/user/Desktop/code/Ops`; branch `codex/opspilot-full`; base `6330f32`.
Схема `0018_lifecycle`; graphs v1/v2, DTO/state1, checkpoint SDK9 сохранены.
[Итоговые проверки](full/evidence/f17/checks.json), [контракты](full/f17-security-contracts.md),
[операции и восстановление](full/f17-operations.md).

Реализованы bounded tenant-admin preview/apply с точным digest, проектные сроки30/90/365,
удаление evidence/checkpoints/history/human-command payload и tombstones с бессрочным
сохранением anti-replay идентичностей. Pending/unknown/jobs/leases защищены общей
maintenance-сериализацией. Экспорт —100 строк allowlisted metadata, без payload/секретов;
preview/compact/export оставляют body-free administrative audit. Реальный non-dev OpenBao
с native TLS, ACL и encrypted Raft; rotation/revoke/seal/restart/fresh encrypted restore15/15;
два реально claimed jobs разных tenant завершают MCP write после rotation ровно один раз.

Security: SEC-04/05/06/10 и общие SEC-01/10. Все253 inherited ASVS-поля/owners/N/A сохранены;
102 scoped reviews и24 primary contributions проверены в f17_* полях backlog без объявления
целых требований закрытыми. Crypto/package/image inventory и patch policy сохранены.
Финальные app/web/Redis/IdP/PostgreSQL/manager exact-image raw HIGH/CRITICAL0;
Python/npm audits0, исключений CVE0. Устранены новые системные findings в PostgreSQL,
web и IdP; manager собран с проверенным source backport, metadata не скрыта.

Приёмка объединяет F02–F17: основной backend run451 pass/1 trace failure/11 dedicated skips;
после исправления bounded collector admission — финальные16/16 lifecycle/observability,
172 unit, Ruff/format/mypy134; browser24, queue5, fencing3, provider crash1, Redis stop/recreate1,
native TLS8 + collector12 + Redis6 + MFA/browser14; scripted eval12/12. Первоначальный
пропуск command trace исследован: новый служебный lock span исключён из detail tracing,
trace batch повторяется только при доказанном отказе до admission; неизвестные результаты
не повторяются. Границы очереди, native mTLS, redaction и проверка journal chain сохранены.
Финальный живой OIDC/scripted smoke с command.process/integrity прошёл.

Существующая Full: encrypted offline physical backup восстановлен исходным образом;
затем logical restore в новый PostgreSQL16 volume при смене libc. Counts/SHA256 всех15
legacy tables совпали до/после schema upgrade до запуска workers/smoke. Старый физический
volume и recovery artifacts сохранены; retention к существующим Full данным не применялся.
MVP: main/HEAD f9f8d79,184 файлов с env, images и volume metadata/content не изменены.
Тесты использовали собственные opspilot-full-test-* / security-f17-final2 profiles.

Только scripted/synthetic local calls и публичные software/advisory downloads; платных
model calls, vendor writes, remote CI, production deployment и push не было. Docker restart
для восстановления Engine ранее явно разрешён пользователем. Service tokens manager
истекают через час и обновляются оператором; production custody/off-host recovery,
нагрузочный SLA/F21, F18–F24 и полный ASVS L2 остаются вне закрытого scope.
Отдельный локальный commit subject: `feat(full): complete F17 lifecycle and Core security acceptance`.


## F18 — принято 7 ноября 2026 года

Base `017b68bb34e85e95013076d570bd14b5519f842b`; отдельный локальный commit subject
`feat(full): complete F18 adapter platform and signed ingress`; push не выполняется.
[Checks](full/evidence/f18/checks.json), [contracts](full/f18-security-contracts.md),
[operations](full/f18-operations.md), [crypto inventory](full/f18-crypto-inventory.json).

Реализованы tenant-admin CAS config/immutable mapping1, computed credential refs, exact-path real
manager ACL, bounded HTTP/TLS adapter и persisted circuit breaker. Raw-body HMAC256 с timestamp/kid/
rotation, constant-time check и immutable event/body identity; receipt+job commit до2xx. Отдельный
processor обрабатывает только typed synthetic observations, монотонный cursor, quarantine при disable;
role не имеет domain/workflow privileges, webhook не даёт approval/business write. Public Nginx
проксирует raw bytes с method/body/time bounds. MCP13, graphs v1/v2, DTO/state1, checkpoint SDK9 прежние.

SEC-04/09 + SEC-01/10: transport33; backend486/44 dedicated skips (33 F18 отдельно +11 inherited),
unit200; browser24, queue5/fencing3/provider crash1/Redis restart1, eval12/12 (0 unauthorized writes,
duplicates и false verified success). Native TLS8/collector12/Redis6/MFA14/IdP policy4 плюс позитивный
F18 HTTPS ingress → manager → verify-full PG/CLI. Manager ACL9 и overlap/retirement/in-flight/revoke.
Все6 runtime images raw H/C0, package audits pass; artifact/runtime secret matches0.

Все253 inherited ASVS fields/owners/baselines/N/A сохранены; добавлены102 scope reviews и5 primary
local contributions без whole-norm closure. [Proof](full/evidence/f18/asvs-baseline-check.json).
Full Pilot/полный L2 остаются NOT_MET; production firewall, vendor/staging/live и последующие gates
не закрыты. Simulator явно synthetic, write/native-idempotency false, credential expiry unknown.

Main Full мигрирован до0019 после encrypted backup/fresh offline restore и проверки всех48 legacy
таблиц/columns/counts/SHA256. Default registry пустой, vendor вызовы не включены; отдельный worker
без business/MCP/manager credentials. UI/API200, реальный OIDC/scripted/refresh smoke принят.
MVP source/env/branch/HEAD/images/volumes не изменены; исходный Full volume сохранён.

Прежние failed/interrupted проверки не скрыты: stale file-grant tamper harness исправлен на actual
manager key; FOR SHARE reader privilege исправлен узкой trusted-tenant функцией; browser/process
вынесены на свежую БД после сохранённого negative-fencing fixture claim. Docker memory/pool limits
устранены serial gates и явной проверенной native subnet, без reset/удаления данных/сетей.
Подробнее — [verification history](full/evidence/f18/README.md).

На завершение F18: F19–F24 не начаты. Актуальное состояние F19 приведено ниже.

## F19 — локальная часть принята; staging gate открыт

Пользователь явно разрешил локальную часть и отложил staging. Код/schema0020 проверены только
в изолированных test projects, app/tests/prometheus:f19. Main Full остаётся F18/schema0019,
все6 принятых runtime tags сохранены. MVP неизменён; push/paid calls/vendor writes/remote CI нет.

Fixed scoped queries, expected-target/sample-age normalization, unknown expiry/absent/stale/partial,
bounded ranges/cardinality/body/deadlines, immutable mapping и manager-backed read credentials.
Настоящий Prometheus3.16.0 читает synthetic series; UI/MCP/facts сохраняют provenance и не выдают
metric samples за delivery events. Native Basic Auth не даёт upstream label RLS — staging scope
требует отдельной проверки tenant-isolated source/gateway.

Backend527/74 dedicated skips; final patched native287 (unit257 + contracts30), browser1;
Ruff/format231, mypy150; source/image150 app/81 tests/21 migrations; ASVS253 inherited fields intact,
scoped contributions85/primary5. Original Prometheus image с2 HIGH исправлен checksum-pinned
source rebuild/x-net0.62.0; final app/Prometheus raw H/C0, Python/npm audits0 vulnerabilities.
Неблокирующие raw MEDIUM(zlib)/UNKNOWN(x/crypto) сохранены; полный L2 NOT_MET.

[Checks](full/evidence/f19/checks.json), [contracts](full/f19-security-contracts.md),
[operations](full/f19-operations.md), [image remediation](full/f19-prometheus-image.md).
Для F19 done нужен отдельный authorized staging endpoint/credentials/mapping и redacted actual
version/scope/MCP/UI evidence. Не называть local synthetic series live. F20 не начинался.


## F19 — authorized AWS staging completion, 7 ноября 2026

Workspace `C:/Users/user/Desktop/code/Ops`, branch `codex/opspilot-full`, base `c984d6a`.
По отдельному разрешению владельца использован один временный t3.small/20GiB encrypted gp3/
public IPv4 в il-central-1, максимум24h/USD5, с последующим удалением. Прежняя запись о deferred
staging выше историческая; она заменена текущим результатом. F20 не начат.

Настоящий checksum-pinned Prometheus3.16.0 измерял readiness двух принадлежащих staging HTTP
сервисов с disk write/read/fsync. Это observed staging, а не customer/live delivery data.
Явные mapping/expected targets, HTTPS с отдельным CA/IP SAN, Basic read auth, operator /32,
IMDSv2, без instance role и без outbound SG rules. Ключи/credentials только в ignored `.tools`.
MCP имеет exact read-only test-manager ACL; app/worker не получают upstream secret.

Три полных smoke прогона: healthy, остановленная replica → unavailable, recovery → healthy;
каждый проверяет auth/tenant scope, absent/stale/partial unknown, unknown credential expiry,
MCP provenance. Real-OIDC browser1 passed на работающем lab: scripted cost0, no action,
observed:staging и неизменные evidence после refresh. Два холодных browser запуска дали ошибки
зависимости; это сохранённое ограничение, не load/soak/reliability acceptance. Transport budgets
не ослаблялись. Изменение runner добавляет connector readiness smoke перед browser; эта
последняя перестановка отдельно на удалённом endpoint не перезапускалась после cleanup.

Отдельный test project `opspilot-full-test-f19-aws-r1`, schema0020; main Full остаётся F18/0019,
без rebuild/seed/migrations. Test volumes сохранены, lab остановлен. SEC-09 scope и SEC-01/10:
253 inherited ASVS identities/fields сохранены, secret/static/isolation checks отдельные.
Полный L2/Pilot по-прежнему NOT_MET. [Evidence и ограничения](full/evidence/f19-aws/README.md).
AWS inventory подтвердил terminated instance, ноль созданных EBS/ENI/VPC/subnet/SG/routes/IGW/keypairs.
Верхняя оценка compute/disk/IPv4 до credits ~$0.152; billing ещё может запаздывать.
MVP184 source/env fingerprints, branch/HEAD, images и volumes сохранены. Без push.
Отдельный stage commit subject: `feat(full): verify F19 authorized AWS staging and cleanup`.


## F20 — sandbox discovery and offline preparation, 8 ноября 2026

Base `830ef61`; `C:/Users/user/Desktop/code/Ops`, `codex/opspilot-full`.
F20 разрешён текущим запросом; F21–F24 не начаты. Статус **blocked**, не done.
[Подготовка и remaining gates](full/f20-jira-preparation.md).

В доступных environment/.env отсутствуют Jira/Atlassian key names; в `.tools` нет
файлов с Jira/Atlassian в имени. Значения секретов не печатались. Atlassian plugin
найден, но installed=false; подключение не подтверждено. Это не доказательство
отсутствия sandbox у владельца: доступного site/project/credential scope нет.
Никакие Jira проекты не читались и не изменялись; vendor/model paid calls/push0.

Добавлен только offline payload helper: fixed project/type/fields, deterministic ADF,
operation property, digest destination/mapping/version/exact bytes. Он не зарегистрирован
в runtime и не даёт write capability. Durable dispatch/reconciliation, comment,
manager/grant/MCP/UI wiring, simulator/security gates и live acceptance ещё не реализованы.
Ruff format/check passed; pytest tests/test_f20_jira_payload.py:6 passed.
253 ASVS backlog rows не изменялись; scoped security acceptance не заявлен.
Docker isolation gate дважды не смог прочитать inventory: Linux Engine pipe отсутствует.
Desktop запущен hidden, но Engine не был готов на повторной проверке. Builds/migrations,
seed, dev restart не выполнялись. Source/env/head MVP проверены отдельно; images/volumes
на этот момент не подтверждены заново. Main Full остаётся F18/schema0019.
Локальный preparation commit subject: `feat(full-f20): prepare offline Jira payload contract`.


### F20 — подтверждённый test site, token scope blocker; 8 ноября 2026

Base a9e50bf; Ops/codex/opspilot-full. Owner создал отдельную Jira Free и KAN/OpsPilot Test,
предоставил credential локальным файлом. Atlassian plugin не нужен. GET mypermissions200
подтвердил valid credential и Browse/Create/Add Comments. GET project/issue/myself401:
provider сообщает scope mismatch. Ошибка прежнего agent списка17 scopes признана;
официальная OpenAPI показывает12 недостающих зависимостей (29 total), не invalid token.
[Preflight](full/evidence/f20/jira-preflight.json), [scope gap](full/evidence/f20/scope-gap.json).

Добавлены read-only preflight, comment payload и pure exact issue/comment/marker verification,
узкая ADF normalization, conservative unknown/multiple-match rules. Не подключены к runtime;
PostgreSQL dispatch_started/one attempt/late-response, pinned transport, manager/grant/MCP/UI,
fault simulator и реальные reject/approve/comment/replay gates ещё требуют реализации.
F20 **blocked**, не done; Full L2/Pilot NOT_MET. Подробности: full/f20-jira-preparation.md.

Scoped tests21 passed; Ruff/format и mypy2 passed. Historical tests не изменены.
Broad host unit attempts прерваны на inherited thread-timeout test после26 pass; результаты
не приняты. Initial targeted tmp permission issue исправлен workspace basetemp.
MVP existing isolation gate184 files/env/head/images/volume metadata/content passed;
report .tools/verification/f20-isolation-before.json. Builds/migrations/dev updates0,
main Full schema0019. Jira writes/paid calls/remote CI/push0; ASVS253 backlog unchanged.
Local continuation commit subject: `feat(full-f20): verify sandbox access and exact result contracts`.


## F21 — локальные измерения и оставшиеся blockers, 8 ноября 2026

Base152d59b; C:/Users/user/Desktop/code/Ops, codex/opspilot-full. Пользователь явно
запросил F21, пока F20 incomplete и real Jira gate отложен; стандартный выбор первого
незакрытого этапа этим запросом переопределён, F20 не объявлен done.
[Контракты/ограничения](full/f21-resilience-contracts.md).

Изолированный lab opspilot-full-test-f21-r4/subnet30/schema0021, новый F21-only manager.
MVP сохранён по prerequisite gate; main Full остаётся0019 без rebuild/migration/seed.
Найдены и исправлены admission/maintenance lock inversion и per-request API enqueue pools.
Обе regression probes2 passed; первоначальный исправленный smoke100create/100decision,
20runs/40jobs terminal и0unsafe/duplicate/false-verified прошёл. Следующий100-distinct
burst выявил PostgreSQL connection exhaustion; после shared pool fix32accepted/68bounded429,
без500. Все failed attempts сохраняются.

Принятый soak1800.009sec:100 paced runs/200 jobs, подтверждено независимым DB audit.
Всего harness153 completed runs/306 done jobs;0duplicate/unauthorized/rejected writes,
false verification и attention без причины.2API+2workers+2tenant,100 concurrent create/
decision requests,20observed active nonterminal runs. Create p95=3.177s, decision3.876s,
paced completion8.625s. MCP/Redis/collector/PostgreSQL stop/recovery измерены отдельно;
worker spawn и API readiness timings не приравниваются к job recovery. Fixture sessions,
scripted workload; IdP login load/HA/quorum/SLO не заявлены. Подробные counts/limits:
[checks](full/evidence/f21/checks.json), [отчёт](full/evidence/f21/README.md).

278 unit tests passed; fault suite114 passed/1 skipped, fencing3 passed в fresh r7/subnet33.
Fault suite использует отдельный r6/subnet32; rolling legacy/new
workers сохранили pinned v1/v2, natural immutable expiry,0expired writes. Initial r5
fixture пыталась изменить immutable expiry и была правильно отклонена; failed XML сохранён,
guard не ослаблен. Source hashes152 фактически импортированных файлов зафиксированы.
Main Full0019 не мигрирован/пересобран; текущие источники тестировались read-only mounts.

SEC-02/03/05/07/09/11 + общие SEC-01/10: scoped adversarial/fencing/telemetry gates,
fresh image/Python audit, secret scan и253 ASVS inherited-field comparison в evidence.
Python audit0; app/PostgreSQL/Redis0HIGH/CRITICAL. **Manager x/net0.61.0 содержит HIGH
CVE-2026-78661 (исправление0.62.0)**. Security gate NOT_MET, applicability exception нет.
При менее3GB свободного диска тяжёлая пересборка manager не выполнялась, существующие
images/volumes не удалялись ради неё. Второй blocker — F20 write/one-attempt/reconciliation
ещё не реализован, real Jira gate явно отложен владельцем. Поэтому F21 **blocked**, не done.
Full L2/Pilot NOT_MET; F22 не начат. MVP184 files/env/head/images/volume content сохранён.
Все F21 контейнеры остановлены; images/networks/volumes сохранены, чужие проекты не выбирались.
Paid/vendor calls/remote CI/push0. Отдельный локальный commit subject:
`feat(full-f21): measure bounded load recovery and repair admission bottlenecks`.

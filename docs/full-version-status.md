# OpsPilot Full — статус реализации

Дата создания: 26 октября 2026 года. **F01–F08 завершены; F09–F24 не начаты.**

Источник требований: [OpsPilot_Full_Project_Specification.md](../OpsPilot_Full_Project_Specification.md).
Portfolio MVP завершён отдельно; его статус — [implementation-status.md](implementation-status.md).
Опорный MVP-коммит: `01019b6`. Новый план не обнуляет прежние этапы 1–8.

## Где выполнять работу

Канонический tracker находится в Full worktree:
`C:\Users\user\.codex\worktrees\opspilot-full-f01\AI Incident & Operations Agent`,
ветка `codex/opspilot-full`, planning base `f9f8d79f572a575dd0f86c40986e7ae13ebb45c9`.
В исходном MVP checkout создан игнорируемый `.tools/opspilot-full-workspace.json` с путём,
веткой, base_commit, compose_project и status_file, без credentials.
Исходная planning-копия tracker в MVP намеренно не меняется.

До проверки изоляции запрещены миграции, сборка образов и изменение приложения ради Full.
MVP `.env`, UI 8081, БД, volumes, images, source/media и ветка сохраняются.

## Текущая очередь

**Следующий этап: F09 — action revisions, approval и grants. Не начат.**

Команда для следующего этапа (пока не выполнять):

> Сделай F09 полной версии OpsPilot по OpsPilot_Full_Project_Specification.md, сохранив MVP.

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

| ID | Статус | Результат этапа | Evidence / commit |
| --- | --- | --- | --- |
| F01 | done | Отдельные worktree/ресурсы Full, сохранённый MVP, baseline/contracts | [evidence](full/evidence/f01.md); commit subject: `feat(full): isolate F01 foundation and preserve portfolio MVP` |
| F02 | done | Tenant schema/RLS/upgrade fixtures | [evidence](full/evidence/f02/README.md); commit subject: `feat(full): add F02 tenant isolation and safe fixture upgrades` |
| F03 | done | OIDC, sessions, memberships/роли | [evidence](full/evidence/f03/README.md); commit subject: `feat(full): implement F03 OIDC sessions and tenant roles` |
| F04 | done | Сквозная API/MCP authorization | [evidence](full/evidence/f04/README.md); commit subject: `feat(full): enforce F04 API and scoped MCP authorization` |
| F05 | done | Durable jobs, отдельный worker | [evidence](full/evidence/f05/README.md); commit subject: `feat(full): implement F05 durable jobs and independent worker` |
| F06 | done | Multiworker leases/fenced checkpoints | [evidence](full/evidence/f06/README.md); commit subject: `feat(full): implement F06 multiworker leases and fenced checkpoints` |
| F07 | done | Transactional events/audit/projections | [evidence](full/evidence/f07/README.md); commit subject: `feat(full): implement F07 transactional events audit and projections` |
| F08 | done | Durable typed clarification и cancellation | [evidence](full/evidence/f08/README.md); commit subject: `feat(full): implement F08 durable clarification and cancellation` |
| F09 | not_started | Revisions/TTL/approval/grants | — |
| F10 | not_started | Local ticket/comment/internal inbox writes | — |
| F11 | not_started | Mixed plans/dependencies/approval waves | — |
| F12 | not_started | Freshness/expiry/revocation/replan | — |
| F13 | not_started | SSE replay/reconnect и авторизация | — |
| F14 | not_started | Полный UI/история/inbox/admin | — |
| F15 | not_started | Redis/limits/durable usage/cost | — |
| F16 | not_started | Traces/metrics/operator diagnostics | — |
| F17 | not_started | Retention/rotation/Full Core acceptance | — |
| F18 | not_started | Adapters и signed durable ingress | — |
| F19 | not_started | Authorized Prometheus read connector | — |
| F20 | not_started | Authorized Jira sandbox writes/reconciliation | — |
| F21 | not_started | Fault/concurrency/load/soak evidence | — |
| F22 | not_started | 50 evals и отдельный real/holdout report | — |
| F23 | not_started | Pilot deployment/TLS/backup/restore | — |
| F24 | not_started | Full Pilot release и traceability | — |

## Запись результата этапа

При выполнении обновлять таблицу и добавлять ниже запись по этому шаблону:

```text
FNN — название
Дата; абсолютный worktree path; branch; base SHA; workflow/policy/schema versions.
Что реализовано и какие требования спецификации закрыты.
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

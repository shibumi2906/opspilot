# OpsPilot Full — статус реализации

Дата создания: 26 октября 2026 года. **F01 завершён; F02–F24 не начаты.**

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

**Следующий этап: F02 — Tenant schema/RLS/upgrade fixtures. Не начат.**

Команда для следующего этапа (пока не выполнять):

> Сделай F02 полной версии OpsPilot по OpsPilot_Full_Project_Specification.md, сохранив MVP.

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
| F02 | not_started | Tenant schema/RLS/upgrade fixtures | — |
| F03 | not_started | OIDC, sessions, memberships/роли | — |
| F04 | not_started | Сквозная API/MCP authorization | — |
| F05 | not_started | Durable jobs, отдельный worker | — |
| F06 | not_started | Multiworker leases/fenced checkpoints | — |
| F07 | not_started | Transactional events/audit/projections | — |
| F08 | not_started | Clarification и cancellation | — |
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

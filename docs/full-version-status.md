# OpsPilot Full — статус реализации

Дата создания: 26 октября 2026 года. **Реализация Full ещё не начата.**

Источник требований: [OpsPilot_Full_Project_Specification.md](../OpsPilot_Full_Project_Specification.md).
Portfolio MVP завершён отдельно; его статус — [implementation-status.md](implementation-status.md).
Опорный MVP-коммит: `01019b6`. Новый план не обнуляет прежние этапы 1–8.

## Где выполнять работу

Сейчас этот файл — planning tracker в исходном MVP checkout. F01 должен создать отдельный
Full worktree/ветку `codex/opspilot-full` и локальный игнорируемый указатель
`.tools/opspilot-full-workspace.json` в исходном checkout. После этого **канонический tracker —
этот файл в Full worktree**, а не его исходная planning-копия. В указателе сохраняются абсолютный
путь, branch, base_commit, compose_project и status_file; credentials туда не записываются.

До проверки изоляции запрещены миграции, сборка образов и изменение приложения ради Full.
MVP `.env`, UI 8081, БД, volumes, images, source/media и ветка сохраняются.

## Текущая очередь

**Следующий этап: F01 — изоляция MVP и база Full.**

Команда для начала:

> Сделай F01 полной версии OpsPilot по OpsPilot_Full_Project_Specification.md, сохранив MVP.

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
| F01 | not_started | Отдельные worktree/ресурсы Full, сохранённый MVP, baseline/contracts | — |
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

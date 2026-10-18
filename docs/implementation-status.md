# Статус реализации Portfolio MVP

Источник требований: `OpsPilot_Portfolio_MVP_plan.md`. Дата работы: 18 октября 2026.

| Этап | Статус | Результат |
| --- | --- | --- |
| 1 | done | Окружение, миграция, fixtures, MCP server/client и readiness проверены; 23 теста прошли |
| 2 | done | Восемь read-tools, FTS, evidence и CLI; 48 тестов прошли |
| 3 | done | LangGraph, checkpoints, providers и CLI; 94 теста и полный live smoke прошли |
| 4 | done | Immutable action, PostgreSQL interrupt, background API, Approve/Reject и singleton guard |
| 5 | done | Atomic MCP create_ticket, approval barrier, replay и exact get_ticket verification |
| 6 | done | React UI, same-origin proxy, live progress; 122 Python tests + 9 Playwright scenarios passed |
| 7 | not_started | Restart recovery и traces |
| 8 | not_started | 12 eval cases, CI и release materials |

## Этап 1: реализация

- Python package, frozen lock, Docker runtime без root и Compose.
- PostgreSQL schemas domain/workflow/checkpoints, отдельные ограниченные роли приложения.
- Начальная Alembic migration с восемью прикладными таблицами, FK/unique/check constraints.
- Seed с фиксированными UUID: 3 клиента, 3 интеграции, 10 incidents, 5 articles.
- Повторный seed upsert; синтетические monitoring observations от scenario clock.
- Настоящий MCP Streamable HTTP `/mcp`, server auth до dispatch, strict discovery schemas,
  get_customer с typed structured results, error isError и source references.
- MCP SDK client: initialize/discovery/call, allowlist и response schema validation.
- FastAPI `/health`: DB, migration revision и реальный MCP discovery.
- Изолированный test stack, не публикующий host ports и использующий отдельный volume/DB.

Административные операции вынесены в одноразовый Compose service `admin`. API container
не получает migration/domain credentials. Это уточнение quickstart исходного плана:
миграции и seed запускаются через admin, обычный runtime остаётся ограниченным.

## Команды воспроизведения

```powershell
docker compose build
docker compose up -d --wait postgres
docker compose run --rm admin
docker compose run --rm admin python -m opspilot.cli.seed
docker compose run --rm admin python -m opspilot.cli.seed
docker compose up -d mcp api
docker compose exec api python -m opspilot.cli.mcp_smoke
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/test-stage1.ps1
```

Test script использует отдельный проект `opspilot-test` и database `opspilot_test`.
Он собирает test image, поднимает БД, применяет migration, seed, запускает API/MCP,
выполняет pytest и останавливает тестовые сервисы. Volume сохраняется для диагностики.
Regular demo данные не удаляются и не используются integration tests.

Локальные проверки: `uv sync --frozen`, `uv run ruff check .`,
`uv run ruff format --check src tests migrations`, `uv run mypy src`,
`uv run pytest tests/unit -q`. Integration tests вне isolated environment пропускаются;
это не считается их успешным прогоном.

## Фактические результаты проверок

18 октября 2026, финальный прогон:

| Проверка | Результат |
| --- | --- |
| Docker build runtime/test images | Успешно, Python 3.12.15 |
| Migration на пустую PostgreSQL 16.15 | 0001_domain_workflow применена |
| Повторный seed | 3 customers / 10 incidents / 5 articles; без дубликатов |
| `scripts/test-stage1.ps1` | **23 passed in 4.28s**, без warnings; exit 0 |
| Ruff check | All checks passed |
| Ruff format check | 35 files already formatted |
| mypy src | Success, 27 source files |
| MCP SDK smoke | protocol 2025-11-25, get_customer GreenShop, NOT_FOUND для отсутствующего UUID |
| API health | HTTP 200; database/migrations/mcp = ready |
| Host network exposure | Только API 127.0.0.1:8000; MCP и PostgreSQL без host ports |
| Проверка локальных secret values | Не обнаружены в исходниках, тестах, документации, Compose и lockfile |

В suite входят реальный transport, отказ при missing/invalid credential, запрет extra
arguments/invalid UUID, повторный seed с сохранением посторонней записи, отсутствие tickets,
ограничения runtime DB ролей и совместимость StateGraph/AsyncPostgresSaver в schema checkpoints.
Последние два компонента проверены вместе на реальной БД, но это не граф расследования.

## Известные границы

Реализованы этапы 1–3. Доступны восемь read-tools и CLI расследования; нет runs API,
записи тикетов, approval, UI или production authentication.
CLI использует настоящий StateGraph и runtime setup AsyncPostgresSaver в schema checkpoints.
Restart recovery ожидающего approval относится к следующим этапам.

`.env` создан локально со случайными секретами, игнорируется Git и Docker build context.
Образы и protocol версии записаны в dependencies.md. Реальный LLM не использовался.

## Этап 2: реализация и проверка

18 октября 2026. Добавлены все восемь read-tools, strict argument/data contracts,
точная сверка discovery, migration `0002_search_indexes` с RU/EN GIN FTS indexes,
фильтры language/integration/customer и стабильная сортировка. Monitoring проверяет
customer/integration в БД до чтения; overlays задаются только серверной конфигурацией.

`cli.diagnose` выполняет lookup → customer → status/events → incidents/docs → credential.
Точное имя GreenShop разрешается однозначно; Green возвращает кандидатов.
Нормализатор evidence сохраняет source identity/version, excerpt, content hash,
scenario timestamp и tool_call_id. ID включает namespace run и hash content;
standalone normalizer использует нулевой namespace по умолчанию.
Ошибки/timeout не порождают evidence. Unknown остаётся успешным наблюдением.

Восемь read-tools доступны через настоящий MCP; write tool отсутствует. LLM, graph,
approval и UI относятся к следующим этапам. Runtime health требует revision 0002.

Проверка: `scripts/test-stage2.ps1` запускает весь suite этапов 1–2 в отдельной БД.
Финальный Docker-прогон: **48 passed in 5.90s**, exit 0, без warnings.
Из них 24 unit tests; остальные — transport/contract/integration с настоящей PostgreSQL.
Ruff check и format check проходят; mypy: 33 source files без ошибок.
Проверены discovery восьми инструментов, RU/EN retrieval, фильтры и пустая выдача,
401/expired, half-open event range/limit, NOT_FOUND для чужой integration и ticket,
ambiguous lookup, raw extra arguments и limit violations, все monitoring overlays
через HTTP, timeout CLI с missing checks и отсутствие tickets после повторного чтения.
Тестовые сервисы остановлены, volume сохранён. Demo stack не изменён.

## Этап 3: реализация и проверка

18 октября 2026. Отдельные узлы classify, resolve_customer, investigate, execute_reads,
reason, plan, risk_check, report; conditional edges и исследовательский цикл.
Typed state и strict classification/decision/analysis/proposal/report; reducers upsert по ID.
Provider выбирает read-tools, код проверяет allowlist, аргументы и resolved scope до dispatch.
Факты допускаются из канонических наблюдений с evidence; ссылки гипотез и customer/поля
предложения проверяются независимо. История помечена как историческая; гипотезы отделены
от фактов. Proposal строится из проверенного контекста и не исполняется.

PostgreSQL checkpointer выполняет setup до invoke, thread_id=run_id. CLI сохраняет run,
результат, observations и usage в workflow; повтор completed client_request_id идемпотентен.
Domain читается только через MCP. Бюджеты и reserved verification read проверяет код,
включая retries, invalid outputs, tokens и monotonic active time. Unknown usage явный.
Ошибки провайдера сохраняются безопасными codes, без body/headers или credentials.

Scripted mode использует fixture decisions с настоящими graph/MCP/БД.
Real mode: OpenAI Responses API, function calling и strict structured outputs.
Модель задаёт OPENAI_MODEL; secret только в ignored .env и API environment.
Автоматический suite не вызывает оплачиваемую модель; smoke выполняется отдельно.

Полный Docker-прогон после regression fixes: **94 passed in 15.35s**, exit 0, без warnings.
Ruff check/format проходят; mypy: 60 source files без ошибок. Проверены RU/EN GreenShop,
настоящие сохранённые checkpoints, research cycle/conditional edges, status-only, unknown/
ambiguous customers, healthy/unknown/timeout/contradictory monitoring, запрет неизвестных
и write-tools, бюджеты, повтор client_request_id, token/unknown usage, invalid outputs,
replay reducers, fake evidence и отсутствие бизнес-записей.

## Live smoke этапа 3

18 октября 2026, после явного разрешения пользователя на передачу синтетических данных.
Провайдер OpenAI Responses API, фактическая модель `gpt-5.6-terra`.
Запрос: `Investigate why GreenShop orders fail today`.

Run: `32b8cb69-10a7-42d8-a3f7-5ee7f48640e3`; outcome=`proposed_only`.
7 настоящих MCP reads, 5 investigation rounds, 8 model attempts; 14789 input + 1807 output
токенов; unknown usage=0; active time=18.097 s. Есть все пять видов domain evidence:
status, events/401, credential/expired, incident history, knowledge/runbook.
В отчёте 10 фактов и 1 помеченная гипотеза, missing_checks=[]; proposal относится к GreenShop.
В PostgreSQL сохранены 18 checkpoints; run.status=completed. tickets/actions/approvals=0.
Проверены DTO результата и целостность evidence references.

Smoke выявил преждевременный stop и длинные AND-запросы FTS. Цикл теперь возвращает
недостающие reads при раннем stop, завершает исследование после обязательных чтений,
сохраняет бюджеты и отправляет компактный контекст без дублирования evidence/results.
Описания FTS объясняют короткие query и cross-customer history. Regression suite после
изменения цикла: **94 passed in 15.35s**. FTS descriptions проверены отдельным полным live smoke.

## Основная локальная база данных

БД `opspilot` существует в основной PostgreSQL, volume сохраняется. На момент проверки:
3 customers, 10 incidents, 5 knowledge articles, 0 tickets. Применена migration
`0002_search_indexes`; checkpoint tables инициализированы официальным SDK.
`scripts/setup-local.ps1` воспроизводимо создаёт БД при первом запуске PostgreSQL,
применяет migrations, seed и checkpoint setup, затем поднимает API/MCP.
Создание БД входит в этап 1; runtime checkpoint storage — в этап 3.

`scripts/setup-local.ps1` выполнен на основной БД: exit 0, seed 3/10/5,
checkpoint schema ready, API healthy. Основные PostgreSQL/MCP/API оставлены запущенными.
Пункт 3 этапа 1 в плане явно уточняет создание database и persistent volume.

## Stage 4 implementation (18 October 2026)

- Persist one immutable create_ticket action and pending approval per run, with canonical SHA-256 hash.
- Actual LangGraph interrupt/checkpoint; saved decision resumes the same thread with Command.
- POST runs (queued + background task + request idempotency), GET public snapshot, POST decision.
- One asyncio lock per run; concurrent repeated decisions schedule exactly one resume.
- PostgreSQL singleton advisory lock rejects a second API process.
- Reject -> rejected without execute. Approve -> explicit execution_not_implemented / partial.
- Snapshot preserves the exact action after either decision; no stage-4 path creates a ticket.
- CLI supports --run-id / --action-id / --decision; README documents API and CLI usage.
- Restart recovery remains stage 7; create_ticket and verification remain stage 5.

Validation passed: ruff check, mypy src, and scripts/test-stage4.ps1: **103 passed**
in 26.42 seconds against isolated PostgreSQL/MCP/API. CLI pause/reject and safe
background-failure projection also passed; no live paid LLM run was repeated for this stage.
The suite covers durable interrupt, immutable replay, both decisions, one concurrent resume,
repeated/opposite decisions, wrong-run actions, payload injection, HTTP projection and singleton.

## Stage 5 implementation (18 October 2026)

- MCP exposes one write-tool create_ticket alongside eight read-tools. LLM read binding is unchanged.
- MCP validates run/action/tool, normalized immutable arguments and canonical hash, and the persisted approval.
- SELECT FOR UPDATE on action serializes writes. Ticket insert and execution_result commit atomically.
- A repeated action returns the existing ticket ID; mismatched payload is rejected before replay.
- Execute loads saved arguments from workflow and uses MCP only for domain writes.
- Lost response reconciles the saved operation result; unknown outcome never triggers a new action/write.
- Verification reads get_ticket via MCP, using the reserved read budget and comparing all returned fields.
- Reports distinguish actions_verified, partial/mismatch, and unknown_outcome; order recovery is unconfirmed.
- Existing schema/role grants support stage 5; no new migration or package dependency is required.
- Run scripts/test-stage5.ps1 for the isolated full suite.

Validation passed: ruff check, mypy src, git diff --check and scripts/test-stage5.ps1:
**120 passed in 45.08 seconds** using real PostgreSQL/MCP/API with the scripted provider.
Coverage includes concurrent writes, pending/rejected/missing approval, run/payload/hash
mismatch, raw grant/fault flag rejection, rollback after insert, lost write response,
unknown write status, verification mismatch/missing ticket, reserved verification read,
and repeated HTTP Approve with the same ticket ID. Read/seed checks preserve existing tickets.
No paid real-LLM run was repeated for this stage; UI and restart recovery remain stages 6–7.

## Stage 6 implementation (18 October 2026)

- Two-column React workspace, responsive mobile layout, permanently visible mode and synthetic disclosure.
- AI/Core/Human labels expose the deterministic-core / AI-layer boundary in the actual product.
- Browser request -> live saved steps/evidence -> immutable approval -> exact verified ticket/report.
- URL-based run restoration; one active polling GET with abort/cleanup, backoff and terminal stop.
- Duplicate create requests retain client_request_id; decision errors reconcile before retry.
- Source cards render source text safely and include evidence IDs/timestamps and missing checks.
- nginx same-origin proxy; loopback web/API publication; no frontend MCP or database secrets.
- Backend now publishes bounded progress after each node and exposes a minimal public config.
- Playwright covers real Approve/Reject, pending refresh, duplicate clicks, reconnect, lost responses,
  source text safety, narrow layout and unverified error states. Ticket-count assertions use test DB only.
- Docker/lockfile pins make frontend and Chromium checks reproducible without host npm/browser setup.

Validation: **122 Python tests passed (56.45 s)** against isolated PostgreSQL/MCP/API;
**9 Playwright scenarios passed (46.4 s)** through the real nginx proxy and Chromium.
TypeScript/Vite production build, ruff, mypy and diff checks passed. Desktop and 390px
mobile screenshots were visually inspected; a separate headless Edge smoke passed.
ESM test resolution and HTTP-origin UUID generation issues found during browser validation
were fixed and the complete browser suite rerun successfully. Timeout/incomplete steps
use a warning state, not a green success marker. No paid LLM run was repeated.
The isolated test stack was stopped without deleting its volume. Demo UI was started on
loopback port 8081 because 8080 was occupied; only ignored .env WEB_PORT was adjusted.

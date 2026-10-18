# Статус реализации Portfolio MVP

Источник требований: `OpsPilot_Portfolio_MVP_plan.md`. Дата работы: 18 октября 2026.

| Этап | Статус | Результат |
| --- | --- | --- |
| 1 | done | Окружение, миграция, fixtures, MCP server/client и readiness проверены; 23 теста прошли |
| 2 | done | Восемь read-tools, FTS, evidence и CLI; 48 тестов прошли |
| 3 | implemented | LangGraph, PostgreSQL checkpoint, policy/budgets, providers и CLI; проверка ниже |
| 4 | not_started | Approval interrupt и decision API |
| 5 | not_started | Транзакционный create_ticket и verification |
| 6 | not_started | React UI |
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

Финальный полный Docker-прогон: **92 passed in 16.78s**, exit 0, без warnings.
Ruff check/format проходят; mypy: 59 source files без ошибок. Проверены RU/EN GreenShop,
настоящие сохранённые checkpoints, research cycle/conditional edges, status-only, unknown/
ambiguous customers, healthy/unknown/timeout/contradictory monitoring, запрет неизвестных
и write-tools, бюджеты, повтор client_request_id, token/unknown usage, invalid outputs,
replay reducers, fake evidence и отсутствие бизнес-записей.

Локально настроены модель gpt-5.6-terra и API key. Живой smoke подготовлен, но отправка
payload во внешний OpenAI API отклонена автоматической проверкой одобрения: требуется
явное разрешение передачи синтетических данных. Вызов ещё не выполнен.

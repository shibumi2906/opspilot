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
| 7 | done | Hard-process restart recovery, committed-write reconciliation, OTel/Jaeger и linked continuation; commit 5690992 |
| 8 | done | 129 Python tests, 3 API hard-restart tests, 9 browser scenarios; scripted 12/12 и real 12/12; CI, screenshots и существующее demo |

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

## Stage 7 implementation (18 October 2026)

- Startup recovery runs after singleton lock acquisition and reads checkpoint tasks plus persisted actions/approvals.
- Same pending action/thread survives restart. A committed decision resumes without new consent.
- Committed operation results bypass write dispatch on replay; continuation verifies the same ticket via MCP.
- Unrelated interrupted queued/running runs fail with RESTART_INTERRUPTED; no generic auto-resume.
- Explicit OTel spans cover API, graph nodes, LLM, MCP client/server/tools and DB operation summaries.
- W3C internal propagation and a new linked continuation trace are implemented. No span spans human wait.
- Collector/Jaeger are digest-pinned; UI links depend on actual Jaeger availability. Token unknowns are null.
- No payloads, prompts, SQL, headers, connection strings or exception bodies are deliberately exported.

Validation: 127 Python tests passed (105.01 s); the three dedicated API process tests are
skipped in that suite and run separately with the Compose API stopped. Full browser and
hard-process results are recorded below after completion. The ordinary regression stack
had no Collector: ticket flows succeeded despite exporter outage. Ruff/format/mypy passed.
A live local Jaeger smoke verified real API/graph/LLM/MCP/DB spans and FOLLOWS_FROM reference
from the continuation to investigation. The GreenShop action ended actions_verified.
The in-memory exporter test verifies trace propagation, links and sentinel credential exclusion.

Final stage 7 checks: **9 Playwright scenarios passed (52.9 s)** and **3 real FastAPI
hard-kill/restart scenarios passed (60.25 s)**: pending interrupt, decision commit before
resume, ticket commit before checkpoint. Tests restart actual subprocesses with the normal
singleton guard, then reach the same approved payload and verified ticket. Startup scanning
was subsequently optimized to share one checkpointer across runs; targeted recovery checks
are recorded with that final change. No real-provider request was needed for this stage.

Final optimized recovery implementation: **7 targeted process/recovery tests passed
(60.45 s)**. All final stage 7 checks passed. Stage 7 is complete.

## Stage 8 implementation (18 October 2026)

- Twelve strict data-driven cases E01-E12 live in src/opspilot/evals/scenarios.yaml
  (JSON-compatible YAML). Runner uses the production graph, actual MCP SDK transport and
  isolated opspilot_test database only. It seeds fixtures, temporarily overlays articles,
  restores them in finally, measures DB rows before decisions and after completion, and
  allows read-route variations. Verification reads are excluded from diagnostic metrics.
- Assertions cover required observations, current-versus-historical evidence, ambiguity,
  unsupported canonical facts, budgets, immutable approval, exact tickets and replay.
  Evaluator regression tests reject unapproved/duplicate/false-success synthetic results.
- Reports retain all 12 cases, actual model IDs, clocks, provider errors, dependencies,
  prompt/fixture/scenario hashes, usage, human wait, latency and metric denominators.
  Source identity is parent commit 5690992 with dirty_snapshot=true; reports do not pretend
  to have been produced from a future commit. Supplemental human-wait/error measurements
  for the real report came from those same stored runs, without new provider calls.
- CI runs lint, format, mypy, Python integration/contracts, Playwright, hard-process recovery
  and scripted eval with generated local credentials. Provider secrets are absent from the
  workflow. The workflow has been added; no remote GitHub CI run is claimed.
- new-local-env.ps1 creates independent random secrets and refuses overwrite; setup preserves
  the existing .env and WEB_PORT=8081. README keeps the AI-layer / deterministic-core position.
- docs/assets contains the already recorded browser demo and five screenshots. The WebM is
  1440x1000, VP9, **158.4 seconds**, decoded successfully. It shows actual pending API kill/start,
  same action/hash, Approve/verified ticket and Reject. No further video creation was performed
  after the user's stop instruction. docs/demo.md links the files and reproduction command.

### Measured release checks

A fresh Compose project opspilot-release-final used a new empty PostgreSQL volume and
new generated credentials. Migrations, seed, checkpoint initialization and service startup
passed. The first attempt exposed an unwritable tool-cache path; checks now disable Ruff
cache and put mypy cache under /tmp. The fresh environment was rerun successfully:

| Check | Result |
| --- | --- |
| Runtime/test/UI builds and fresh migration/seed | passed |
| Ruff check/format and mypy | passed; 78 Python source files |
| Full Python suite | **129 passed, 3 dedicated-process skips, 93.43 s** |
| Separate real FastAPI kill/restart suite | **3 passed, 44.11 s** |
| Playwright Chromium | **9 passed, 53.6 s** |
| Scripted eval in fresh environment | **12/12**, hard safety gate passed |
| Final evaluator tests after reporting-only additions | **2 passed, 1.50 s** |
| Final scripted report with measured human wait | **12/12**, hard safety gate passed |
| Real OpenAI Responses eval | **12/12**, actual model gpt-5.6-terra |
| Secret checks | 176 candidate repo files, API/MCP/Collector logs and 2 Jaeger services; 0 leaks |

Real eval used explicit user authorization to send synthetic requests/evidence to
https://api.openai.com/v1/responses. Measured input/output: **92141 / 10258 tokens**;
unknown usage attempts=0. Task completion=12/12; read-route macro precision/recall=1.0/1.0
across 11 eligible cases. Unauthorized writes=0/2; exact approved writes=2/2; duplicates=0;
false verified success=0; unsupported canonical factual claims=0/59. Active latency p50/p95
(nearest rank)=5.867/22.002 s. E08/E09 hypotheses were reviewed: expiration remains unconfirmed
with unknown/valid metadata; current evidence takes priority over stale/injected text.

Reports: docs/eval-reports/scripted.md + .json and real.md + .json. These 12 synthetic cases
are descriptive portfolio evidence, not production safety or latency guarantees. Remaining
limits are unchanged: one API process, no durable queue, bounded approval/committed-result
recovery only, synthetic integrations, no public hosting or production authentication.
All eight Portfolio MVP stages are done; Phase 2 has not been added.

## English narrated demo follow-up (18 October 2026)

At the user's explicit request, added English AI-generated speech to the existing recording;
no browser re-recording or new eval was performed. Output: docs/assets/opspilot-demo-narrated.mp4.
The original silent WebM is unchanged. OpenAI Speech API generated 11 cached WAV segments using
model gpt-4o-mini-tts and built-in voice cedar. Only the synthetic English narration text and
voice instructions were sent; the local API key was not included in artifacts or command lines.
Final assembly is local. Timed narration and measured media metadata are stored beside the MP4.

Verification: 1440x1000 H.264 + mono AAC at 48 kHz; video/audio both 158.4 s, 6,615,971 bytes.
All 11 scene intervals are ordered and nonoverlapping. Maximum tempo adjustment is under 1.10x.
Audio decode/volume check succeeded, peak -1.3 dBFS (no full-scale clipping). Exact API cost is
not asserted because the WAV responses contain no billed token usage. Cached synthesis does
not repeat requests. Documentation explicitly discloses the AI-generated voice.
Application implementation and the previously passed release/eval results are unchanged.

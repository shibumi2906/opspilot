# Проверенные зависимости

Дата: 18 октября 2026. Runtime и transitive dependencies закреплены в `uv.lock`.
Диапазоны в `pyproject.toml` задают совместимую ветку; обычный запуск использует frozen lock.

| Компонент | Фактическая версия |
| --- | --- |
| Python в Docker | 3.12.15, Debian bookworm |
| Python локальных проверок | 3.12.10, Windows |
| PostgreSQL | 16.15 (Debian 16.15-1.pgdg12+2) |
| uv | 0.13.1 |
| FastAPI / Uvicorn | 0.143.3 / 0.54.0 |
| Pydantic / pydantic-settings | 2.14.1 / 2.16.0 |
| SQLAlchemy / Alembic | 2.0.55 / 1.20.0 |
| psycopg / psycopg-pool | 3.3.6 / 3.3.3 |
| MCP Python SDK | 1.30.0, поддерживаемая ветка 1.x |
| MCP protocol согласованный client/server | 2025-11-25 |
| HTTPX | 0.28.1 |
| LangGraph | 1.2.16 |
| LangGraph checkpoint / PostgreSQL saver | 4.3.0 / 3.2.0 |
| LangChain core | 1.6.12 |
| pytest / pytest-asyncio | 9.1.1 / 1.4.0 |
| Ruff / mypy | 0.17.1 / 1.20.2 |

Образы закреплены по digest в Dockerfile и Compose:

- Python: `sha256:34386ef0cb081344d7ec1c103ba398e6e9f64e9ab3a1509accc92a4e24a07258`.
- PostgreSQL: `sha256:0ea6700a3b4f0ae6ce746519073558aed4d88a79d8d07622a9a644946c7319c4`.

Выбрана поддерживаемая ветка MCP 1.x с явным `<2`. Client и server используют одну
версию SDK. Server реализован через официальный low-level `Server` и
`StreamableHTTPSessionManager`, чтобы discovery публиковал точные JSON schemas с
`additionalProperties=false`, а ошибки имели одновременно structured content и isError.
Это настоящий MCP transport, не REST-имитация. Используется только внутренний service
credential; публичная OAuth-интеграция не заявляется.

## Источники и проверка совместимости

- [Официальный SDK, поддерживаемая ветка 1.x](https://github.com/modelcontextprotocol/python-sdk/tree/v1.x).
- [MCP low-level server](https://py.sdk.modelcontextprotocol.io/v1/low-level-server/).
- [uv: Docker и frozen sync](https://docs.astral.sh/uv/guides/integration/docker/).
- [SQLAlchemy: PostgreSQL/psycopg](https://docs.sqlalchemy.org/en/20/dialects/postgresql.html#module-sqlalchemy.dialects.postgresql.psycopg).
- [LangGraph persistence](https://docs.langchain.com/oss/python/langgraph/persistence).

Фактический smoke `docker compose exec api python -m opspilot.cli.mcp_smoke`:
initialize → protocol 2025-11-25 → tools/list → get_customer GreenShop →
get_customer отсутствующего UUID с NOT_FOUND. Конкретный протокол определяется SDK
и результатом handshake, а не датой исходной спецификации.

`test_checkpoint_compatibility.py` проверяет выбранные graph/saver вместе на PostgreSQL:
setup в schema checkpoints, минимальный StateGraph, сохранение и чтение state.
Это compatibility probe; граф расследования появится на этапе 3.

LLM provider/model ID ещё не выбирались: этап 1 не вызывает модель и не требует API key.
Реальный provider smoke относится к этапу 3. OTel/Jaeger/web-зависимости относятся
к последующим этапам и пока не зафиксированы.

## Stage 2 verification (18 October 2026)

No dependency changes. Frozen lock and pinned images are retained. Discovery now exposes
all eight read-tools, with input schemas checked exactly against the client registry.
Migration 0002 adds PostgreSQL RU/EN FTS indexes. Full isolated Docker suite:
`powershell -NoProfile -ExecutionPolicy Bypass -File scripts/test-stage2.ps1`:
**48 passed in 5.90s**, including real HTTP transport overlay tests.

## Stage 3 dependencies and sources

No new dependencies: LangGraph/Postgres saver and HTTPX reuse the frozen lock. The adapter
uses REST directly; no unpinned OpenAI SDK is introduced. Model ID is explicit in .env.

- [Official function calling guide](https://developers.openai.com/api/docs/guides/function-calling).
- [Official structured outputs guide](https://developers.openai.com/api/docs/guides/structured-outputs?api-mode=responses).
- [GPT-5.6 Terra model ID](https://developers.openai.com/api/docs/models/gpt-5.6-terra).

Contract tests cover function calls, strict structured outputs, refusals, incomplete output,
invalid JSON, usage/missing usage and safe errors. Live smoke is recorded separately.

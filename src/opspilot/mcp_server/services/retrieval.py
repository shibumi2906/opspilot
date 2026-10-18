"""Read-only retrieval. Search expressions match migration 0002's GIN indexes."""

from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from opspilot.contracts.tools import SearchDocumentationArgs, SearchIncidentsArgs


# Use an explicit configuration: predictable RU/EN stemming, independent of server defaults.
def vector_sql(kind: str, language: str) -> str:
    fields = (
        "summary || ' ' || root_cause || ' ' || resolution"
        if kind == "incidents"
        else "title || ' ' || body"
    )
    config = "russian" if language == "ru" else "english"
    return f"to_tsvector('{config}'::regconfig, {fields})"


async def search(
    engine: AsyncEngine, args: SearchDocumentationArgs, *, incidents: bool
) -> list[dict[str, Any]]:
    kind = "incidents" if incidents else "knowledge_articles"
    fields = (
        "id AS incident_id, customer_id, summary, root_cause, resolution, occurred_at"
        if incidents
        else "id AS article_id, version, language, title, left(body, 600) AS excerpt"
    )
    branches = []
    params: dict[str, Any] = {"query": args.query, "limit": args.limit}
    for lang in ("ru", "en"):
        if args.language and args.language != lang:
            continue
        vector = vector_sql(kind, lang)
        config = "russian" if lang == "ru" else "english"
        query = f"websearch_to_tsquery('{config}'::regconfig, :query)"
        filters = [f"language = '{lang}'", f"{vector} @@ {query}"]
        if args.integration_type is not None:
            filters.append("integration_type = :integration_type")
            params["integration_type"] = args.integration_type
        if isinstance(args, SearchIncidentsArgs) and args.customer_id is not None:
            filters.append("customer_id = :customer_id")
            params["customer_id"] = args.customer_id
        branches.append(
            f"SELECT {fields}, ts_rank_cd({vector}, {query}) AS score "
            f"FROM domain.{kind} WHERE {' AND '.join(filters)}"
        )
    id_column = "incident_id" if incidents else "article_id"
    ordering = f"score DESC, {'occurred_at DESC, ' if incidents else ''}{id_column}"
    sql = f"SELECT * FROM ({' UNION ALL '.join(branches)}) hits ORDER BY {ordering} LIMIT :limit"
    async with engine.connect() as connection:
        return [dict(row) for row in (await connection.execute(text(sql), params)).mappings()]

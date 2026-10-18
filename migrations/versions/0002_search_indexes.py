"""RU/EN full-text indexes; no mutable search copies or seed changes."""

from alembic import op

revision = "0002_search_indexes"
down_revision = "0001_domain_workflow"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table, fields in (
        ("incidents", "summary || ' ' || root_cause || ' ' || resolution"),
        ("knowledge_articles", "title || ' ' || body"),
    ):
        for lang, config in (("ru", "russian"), ("en", "english")):
            op.execute(
                f"CREATE INDEX ix_{table}_fts_{lang} ON domain.{table} USING gin "
                f"(to_tsvector('{config}'::regconfig, {fields})) WHERE language = '{lang}'"
            )


def downgrade() -> None:
    for table in ("incidents", "knowledge_articles"):
        for lang in ("ru", "en"):
            op.execute(f"DROP INDEX domain.ix_{table}_fts_{lang}")

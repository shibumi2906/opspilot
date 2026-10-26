# Dependency and protocol compatibility (F01)

`uv.lock` and `web/package-lock.json` remain unchanged from the planning base.
Build uses Python 3.12 and `uv sync --frozen`; no dependency upgrade in F01.

| Dependency | Locked version |
| --- | --- |
| MCP Python SDK | 1.30.0 |
| LangGraph | 1.2.16 |
| LangGraph checkpoint PostgreSQL | 3.2.0 |
| psycopg | 3.3.6 |
| SQLAlchemy | 2.0.55 |
| FastAPI | 0.143.3 |
| Pydantic | 2.14.1 |

Real SDK smoke is `tests/contract/test_mcp_protocol.py::test_real_sdk_discovery_and_read`:
Streamable HTTP negotiation must return MCP 2025-11-25, discover the strict registry and read GreenShop.
Integration graph/decision/recovery tests exercise actual LangGraph interrupts and PostgreSQL checkpoints,
not a replacement SDK mock. Async SQLAlchemy's adapted psycopg cursor requires explicit close;
Full's connection identity guard uses that supported DBAPI surface before application SQL.
These checks demonstrate the inherited local baseline; fenced checkpointer compatibility remains F06.
No claim of OIDC/vendor protocol implementation or current vendor compatibility is made by F01.

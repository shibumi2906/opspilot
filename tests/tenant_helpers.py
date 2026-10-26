from uuid import uuid4

from opspilot.db.models_workflow import AgentRun
from opspilot.tenancy.context import DEMO_ACTOR, require_tenant
from opspilot.tenancy.session import TenantSession


async def register_probe(engine, clock, thread):
    async with TenantSession(engine) as session, session.begin():
        session.add(
            AgentRun(
                id=uuid4(),
                tenant_id=require_tenant(),
                actor_id=DEMO_ACTOR,
                client_request_id=uuid4(),
                request="Synthetic SDK probe",
                request_hash="0" * 64,
                language="en",
                status="completed",
                mode="scripted",
                scenario_id="healthy",
                scenario_clock=clock,
                thread_id=thread,
                state_schema_version=1,
                public_snapshot={},
                tool_results={},
                usage={},
            )
        )

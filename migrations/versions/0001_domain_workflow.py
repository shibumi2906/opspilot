"""Initial domain/workflow schema, frozen DDL; checkpoints are owned by their SDK."""

from alembic import op

revision = "0001_domain_workflow"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
CREATE TABLE domain.customers (
    id UUID NOT NULL, 
    name VARCHAR(200) NOT NULL, 
    normalized_name VARCHAR(200) NOT NULL, 
    metadata JSONB NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id)
)

        """
    )
    op.execute("CREATE INDEX ix_customers_normalized_name ON domain.customers (normalized_name)")
    op.execute(
        """
CREATE TABLE domain.knowledge_articles (
    id UUID NOT NULL, 
    title VARCHAR(200) NOT NULL, 
    body TEXT NOT NULL, 
    integration_type VARCHAR(80) NOT NULL, 
    language VARCHAR(10) NOT NULL, 
    version VARCHAR(30) NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id)
)

        """
    )
    op.execute(
        """
CREATE TABLE workflow.agent_runs (
    id UUID NOT NULL, 
    client_request_id UUID NOT NULL, 
    request TEXT NOT NULL, 
    request_hash VARCHAR(64) NOT NULL, 
    language VARCHAR(10) NOT NULL, 
    status VARCHAR(40) NOT NULL, 
    outcome VARCHAR(40), 
    mode VARCHAR(20) NOT NULL, 
    scenario_id VARCHAR(80) NOT NULL, 
    scenario_clock TIMESTAMP WITH TIME ZONE NOT NULL, 
    thread_id VARCHAR(100) NOT NULL, 
    state_schema_version INTEGER NOT NULL, 
    public_snapshot JSONB NOT NULL, 
    tool_results JSONB NOT NULL, 
    usage JSONB NOT NULL, 
    trace_id VARCHAR(32), 
    error JSONB, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    UNIQUE (client_request_id), 
    UNIQUE (thread_id)
)

        """
    )
    op.execute(
        """
CREATE TABLE domain.customer_integrations (
    id UUID NOT NULL, 
    customer_id UUID NOT NULL, 
    integration_type VARCHAR(80) NOT NULL, 
    external_ref VARCHAR(200) NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    UNIQUE (customer_id, integration_type, external_ref), 
    FOREIGN KEY(customer_id) REFERENCES domain.customers (id)
)

        """
    )
    op.execute(
        "CREATE INDEX ix_domain_customer_integrations_customer_id "
        "ON domain.customer_integrations (customer_id)"
    )
    op.execute(
        """
CREATE TABLE domain.incidents (
    id UUID NOT NULL, 
    customer_id UUID NOT NULL, 
    integration_type VARCHAR(80) NOT NULL, 
    language VARCHAR(10) NOT NULL, 
    occurred_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    summary TEXT NOT NULL, 
    root_cause TEXT NOT NULL, 
    resolution TEXT NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(customer_id) REFERENCES domain.customers (id)
)

        """
    )
    op.execute("CREATE INDEX ix_domain_incidents_customer_id ON domain.incidents (customer_id)")
    op.execute(
        """
CREATE TABLE workflow.actions (
    id UUID NOT NULL, 
    run_id UUID NOT NULL, 
    tool_name VARCHAR(40) NOT NULL, 
    arguments JSONB NOT NULL, 
    arguments_hash VARCHAR(64) NOT NULL, 
    execution_status VARCHAR(30) DEFAULT 'not_started' NOT NULL, 
    execution_result JSONB, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    executed_at TIMESTAMP WITH TIME ZONE, 
    PRIMARY KEY (id), 
    CONSTRAINT ck_actions_tool CHECK (tool_name = 'create_ticket'), 
    CONSTRAINT ck_actions_execution_status CHECK (
        execution_status IN ('not_started', 'succeeded', 'failed', 'unknown')),
    UNIQUE (run_id), 
    FOREIGN KEY(run_id) REFERENCES workflow.agent_runs (id)
)

        """
    )
    op.execute(
        """
CREATE TABLE domain.tickets (
    id UUID NOT NULL, 
    customer_id UUID NOT NULL, 
    originating_action_id UUID NOT NULL, 
    title VARCHAR(200) NOT NULL, 
    description TEXT NOT NULL, 
    priority VARCHAR(10) NOT NULL, 
    status VARCHAR(20) DEFAULT 'open' NOT NULL, 
    evidence_ids JSONB NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(customer_id) REFERENCES domain.customers (id), 
    UNIQUE (originating_action_id), 
    FOREIGN KEY(originating_action_id) REFERENCES workflow.actions (id)
)

        """
    )
    op.execute("CREATE INDEX ix_domain_tickets_customer_id ON domain.tickets (customer_id)")
    op.execute(
        """
CREATE TABLE workflow.approvals (
    id UUID NOT NULL, 
    action_id UUID NOT NULL, 
    decision VARCHAR(20) DEFAULT 'pending' NOT NULL, 
    decided_at TIMESTAMP WITH TIME ZONE, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    CONSTRAINT ck_approvals_decision CHECK (decision IN ('pending', 'approved', 'rejected')), 
    UNIQUE (action_id), 
    FOREIGN KEY(action_id) REFERENCES workflow.actions (id)
)

        """
    )
    op.execute("GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA workflow TO ops_workflow")
    op.execute(
        "GRANT SELECT ON workflow.agent_runs, workflow.actions, workflow.approvals TO ops_domain"
    )
    op.execute(
        "GRANT UPDATE (execution_status, execution_result, executed_at) "
        "ON workflow.actions TO ops_domain"
    )
    op.execute("GRANT SELECT ON ALL TABLES IN SCHEMA domain TO ops_domain")
    op.execute("GRANT INSERT ON domain.tickets TO ops_domain")
    op.execute("GRANT SELECT ON workflow.alembic_version TO ops_workflow")
    op.execute(
        "ALTER TABLE domain.tickets ADD CONSTRAINT ck_ticket_priority "
        "CHECK (priority IN ('low','medium','high'))"
    )
    op.execute("ALTER TABLE domain.tickets ADD CONSTRAINT ck_ticket_status CHECK (status = 'open')")


def downgrade() -> None:
    op.execute("DROP TABLE workflow.approvals")
    op.execute("DROP TABLE domain.tickets")
    op.execute("DROP TABLE workflow.actions")
    op.execute("DROP TABLE domain.incidents")
    op.execute("DROP TABLE domain.customer_integrations")
    op.execute("DROP TABLE workflow.agent_runs")
    op.execute("DROP TABLE domain.knowledge_articles")
    op.execute("DROP TABLE domain.customers")

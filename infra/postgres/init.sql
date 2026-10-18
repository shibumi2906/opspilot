\getenv workflow_password WORKFLOW_DB_PASSWORD
\getenv domain_password DOMAIN_DB_PASSWORD
\getenv checkpoint_password CHECKPOINT_DB_PASSWORD
SELECT format('CREATE ROLE ops_workflow LOGIN PASSWORD %L', :'workflow_password') \gexec
SELECT format('CREATE ROLE ops_domain LOGIN PASSWORD %L', :'domain_password') \gexec
SELECT format('CREATE ROLE ops_checkpoint LOGIN PASSWORD %L', :'checkpoint_password') \gexec
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
CREATE SCHEMA domain;
CREATE SCHEMA workflow;
CREATE SCHEMA checkpoints AUTHORIZATION ops_checkpoint;
GRANT USAGE ON SCHEMA workflow TO ops_workflow, ops_domain;
GRANT USAGE ON SCHEMA domain TO ops_domain;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

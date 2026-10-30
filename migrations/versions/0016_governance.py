"""Durable resource reservations, worker admission and cache/source boundaries."""
from alembic import op

revision = "0016_governance"
down_revision = "0015_workspace"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
CREATE OR REPLACE FUNCTION workflow.admit_run() RETURNS trigger
 LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
 DECLARE actor_active integer; tenant_active integer; all_active integer;
 BEGIN
 IF session_user='ops_migration' THEN RETURN NEW; END IF;
 IF NEW.status NOT IN ('queued','running','waiting_for_input','waiting_for_approval','cancelling')
 THEN RETURN NEW; END IF;
 IF TG_OP='UPDATE' THEN
 IF OLD.status IN ('queued','running','waiting_for_input','waiting_for_approval','cancelling')
 AND OLD.actor_id=NEW.actor_id AND OLD.tenant_id=NEW.tenant_id THEN RETURN NEW; END IF;
 END IF;
 PERFORM pg_advisory_xact_lock(1801202610);
 SELECT count(*) INTO actor_active FROM workflow.agent_runs WHERE actor_id=NEW.actor_id
 AND status IN ('queued','running','waiting_for_input','waiting_for_approval','cancelling');
 SELECT count(*) INTO tenant_active FROM workflow.agent_runs WHERE tenant_id=NEW.tenant_id
 AND status IN ('queued','running','waiting_for_input','waiting_for_approval','cancelling');
 SELECT count(*) INTO all_active FROM workflow.agent_runs
 WHERE status IN ('queued','running','waiting_for_input','waiting_for_approval','cancelling');
 IF actor_active>=LEAST(1000,COALESCE(NULLIF(current_setting('app.max_actor_runs',true),''),'8')::int)
 OR tenant_active>=LEAST(5000,COALESCE(NULLIF(current_setting('app.max_tenant_runs',true),''),'64')::int)
 OR all_active>=LEAST(10000,COALESCE(NULLIF(current_setting('app.max_global_runs',true),''),'128')::int)
 THEN RAISE EXCEPTION 'RUN_ADMISSION_LIMIT' USING ERRCODE='P0001'; END IF;
 RETURN NEW; END $$;
DROP TRIGGER admission_budget ON workflow.agent_runs;
CREATE TRIGGER admission_budget BEFORE INSERT OR UPDATE OF status,actor_id,tenant_id
 ON workflow.agent_runs FOR EACH ROW EXECUTE FUNCTION workflow.admit_run();
CREATE TABLE workflow.resource_policy (
 id boolean PRIMARY KEY DEFAULT true CHECK(id),
 worker_global integer NOT NULL CHECK(worker_global BETWEEN 1 AND 32),
 worker_tenant integer NOT NULL CHECK(worker_tenant BETWEEN 1 AND 16),
 worker_actor integer NOT NULL CHECK(worker_actor BETWEEN 1 AND 8),
 source_actor_minute integer NOT NULL CHECK(source_actor_minute BETWEEN 1 AND 1000),
 source_tenant_minute integer NOT NULL CHECK(source_tenant_minute BETWEEN 1 AND 5000),
 source_global_minute integer NOT NULL CHECK(source_global_minute BETWEEN 1 AND 10000),
 llm_actor_hour integer NOT NULL CHECK(llm_actor_hour BETWEEN 1 AND 1000),
 llm_tenant_hour integer NOT NULL CHECK(llm_tenant_hour BETWEEN 1 AND 5000),
 llm_global_hour integer NOT NULL CHECK(llm_global_hour BETWEEN 1 AND 10000),
 tokens_actor_hour bigint NOT NULL CHECK(tokens_actor_hour BETWEEN 1 AND 30000000),
 tokens_tenant_hour bigint NOT NULL CHECK(tokens_tenant_hour BETWEEN 1 AND 100000000),
 tokens_global_hour bigint NOT NULL CHECK(tokens_global_hour BETWEEN 1 AND 300000000),
 spend_run numeric NOT NULL CHECK(spend_run BETWEEN 0 AND .50),
 spend_actor_hour numeric NOT NULL CHECK(spend_actor_hour BETWEEN 0 AND 10),
 spend_tenant_hour numeric NOT NULL CHECK(spend_tenant_hour BETWEEN 0 AND 100),
 spend_global_hour numeric NOT NULL CHECK(spend_global_hour BETWEEN 0 AND 500));
INSERT INTO workflow.resource_policy VALUES(true,4,2,2,600,1800,6000,
 200,1000,3000,600000,3000000,9000000,.50,5,20,100);
CREATE TABLE workflow.model_prices (
 model text NOT NULL, version text NOT NULL, currency text NOT NULL CHECK(currency='USD'),
 effective_at timestamptz NOT NULL, verified_at timestamptz NOT NULL,
 valid_until timestamptz NOT NULL CHECK(valid_until>effective_at), source text NOT NULL,
 input_per_million numeric NOT NULL CHECK(input_per_million>=0),
 cached_per_million numeric NOT NULL CHECK(cached_per_million>=0),
 output_per_million numeric NOT NULL CHECK(output_per_million>=0),
 PRIMARY KEY(model,version));
INSERT INTO workflow.model_prices SELECT m,'2026-10-30-standard','USD','2026-10-30T00:00:00Z',
 '2026-10-30T00:00:00Z','2026-11-29T00:00:00Z','https://developers.openai.com/api/docs/models/gpt-5-mini',
 .25,.025,2 FROM unnest(ARRAY['gpt-5-mini','gpt-5-mini-2025-08-07']) m;
INSERT INTO workflow.model_prices SELECT m,'2026-10-30-standard','USD','2026-10-30T00:00:00Z',
 '2026-10-30T00:00:00Z','2026-11-29T00:00:00Z','https://developers.openai.com/api/docs/models/gpt-5.4-mini',
 .75,.075,4.50 FROM unnest(ARRAY['gpt-5.4-mini','gpt-5.4-mini-2026-03-17']) m;
CREATE TABLE workflow.usage_reservations (
 tenant_id uuid NOT NULL, run_id uuid NOT NULL, actor_id uuid NOT NULL,
 limits jsonb NOT NULL CHECK(jsonb_typeof(limits)='object') CHECK(
 limits ?& ARRAY['reads','rounds','llm_attempts','tokens','active_seconds','recursion_limit']
 AND jsonb_typeof(limits->'reads')='number' AND (limits->>'reads')::int BETWEEN 1 AND 15
 AND jsonb_typeof(limits->'rounds')='number' AND (limits->>'rounds')::int BETWEEN 1 AND 6
 AND jsonb_typeof(limits->'llm_attempts')='number' AND (limits->>'llm_attempts')::int BETWEEN 1 AND 10
 AND jsonb_typeof(limits->'tokens')='number' AND (limits->>'tokens')::int BETWEEN 1 AND 30000
 AND jsonb_typeof(limits->'active_seconds')='number' AND (limits->>'active_seconds')::numeric>0
 AND (limits->>'active_seconds')::numeric<=120
 AND jsonb_typeof(limits->'recursion_limit')='number' AND (limits->>'recursion_limit')::int BETWEEN 10 AND 60),
 base_usage jsonb NOT NULL DEFAULT '{}', reads integer NOT NULL DEFAULT 0 CHECK(reads>=0),
 rounds integer NOT NULL DEFAULT 0 CHECK(rounds>=0), llm integer NOT NULL DEFAULT 0 CHECK(llm>=0),
 active_seconds numeric NOT NULL DEFAULT 0 CHECK(active_seconds>=0),
 PRIMARY KEY(tenant_id,run_id),
 FOREIGN KEY(tenant_id,run_id) REFERENCES workflow.agent_runs(tenant_id,id));
CREATE TABLE workflow.provider_attempts (
 tenant_id uuid NOT NULL, run_id uuid NOT NULL, actor_id uuid NOT NULL,
 attempt_id uuid NOT NULL, epoch bigint NOT NULL,
 model text NOT NULL CHECK(length(model) BETWEEN 1 AND 200),
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 status text NOT NULL DEFAULT 'started' CHECK(status IN ('started','known','unknown')),
 tokens_reserved integer NOT NULL CHECK(tokens_reserved BETWEEN 0 AND 30000),
 input_tokens integer CHECK(input_tokens BETWEEN 0 AND 1000000),
 output_tokens integer CHECK(output_tokens BETWEEN 0 AND 1000000),
 cached_tokens integer CHECK(cached_tokens BETWEEN 0 AND input_tokens),
 held_tokens integer NOT NULL CHECK(held_tokens>=0),
 standard_pricing boolean, price jsonb, known_cost numeric CHECK(known_cost>=0),
 held_cost numeric NOT NULL CHECK(held_cost>=0), served_model text,
 duration_ms integer NOT NULL CHECK(duration_ms BETWEEN 0 AND 120000),
 PRIMARY KEY(tenant_id,attempt_id),
 FOREIGN KEY(tenant_id,run_id) REFERENCES workflow.agent_runs(tenant_id,id));
CREATE INDEX usage_attempt_window ON workflow.provider_attempts(created_at,tenant_id,actor_id);
CREATE INDEX usage_attempt_run ON workflow.provider_attempts(tenant_id,run_id);
CREATE TABLE workflow.source_budgets (
 scope text NOT NULL, bucket timestamptz NOT NULL, used integer NOT NULL CHECK(used>0),
 PRIMARY KEY(scope,bucket));
CREATE TABLE workflow.worker_admission (
 tenant_id uuid PRIMARY KEY, admitted_at timestamptz NOT NULL DEFAULT '-infinity');
CREATE TABLE workflow.cache_objects (
 tenant_id uuid NOT NULL, object_key text NOT NULL CHECK(length(object_key)<=120),
 version bigint NOT NULL DEFAULT 1 CHECK(version>0), PRIMARY KEY(tenant_id,object_key));
CREATE TABLE workflow.cache_generations (
 tenant_id uuid PRIMARY KEY, namespace uuid NOT NULL DEFAULT gen_random_uuid(),
 generation bigint NOT NULL DEFAULT 1 CHECK(generation>0));
INSERT INTO workflow.cache_generations(tenant_id) SELECT id FROM identity.tenants;
INSERT INTO workflow.worker_admission(tenant_id) SELECT id FROM identity.tenants;
""")
    for table in ("usage_reservations", "provider_attempts", "cache_generations", "cache_objects", "worker_admission"):
        op.execute(f"ALTER TABLE workflow.{table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE workflow.{table} FORCE ROW LEVEL SECURITY")
        op.execute(f"""CREATE POLICY tenant_scope ON workflow.{table}
 USING(tenant_id=identity.current_tenant()) WITH CHECK(tenant_id=identity.current_tenant())""")
    op.execute("""
INSERT INTO workflow.usage_reservations(tenant_id,run_id,actor_id,limits,base_usage,reads,rounds,llm,active_seconds)
SELECT tenant_id,id,actor_id,COALESCE(usage->'limits',usage->'command'->'limits',
 '{"rounds": 6,"reads": 15,"llm_attempts": 10,"tokens": 30000,"active_seconds": 120,"recursion_limit": 60}'::jsonb),
 usage,COALESCE((usage->>'read_attempts')::int,0),COALESCE((usage->>'rounds')::int,0),
 COALESCE((usage->>'llm_attempts')::int,0),COALESCE((usage->>'active_seconds')::numeric,0)
FROM workflow.agent_runs;
CREATE FUNCTION workflow.init_usage() RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER
 SET search_path=pg_catalog AS $$ BEGIN
 INSERT INTO workflow.usage_reservations(tenant_id,run_id,actor_id,limits)
 VALUES(NEW.tenant_id,NEW.id,NEW.actor_id,COALESCE(NEW.usage->'command'->'limits',
 '{"rounds": 6,"reads": 15,"llm_attempts": 10,"tokens": 30000,"active_seconds": 120,"recursion_limit": 60}'::jsonb));
 RETURN NEW; END $$;
CREATE TRIGGER init_usage AFTER INSERT ON workflow.agent_runs FOR EACH ROW EXECUTE FUNCTION workflow.init_usage();
CREATE FUNCTION workflow.usage_snapshot(target uuid) RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER
 SET search_path=pg_catalog AS $$
DECLARE r record; a record; base_unknown integer;
BEGIN
 SELECT u.* INTO r FROM workflow.usage_reservations u JOIN workflow.agent_runs g
 ON g.tenant_id=u.tenant_id AND g.id=u.run_id WHERE u.tenant_id=identity.current_tenant()
 AND u.run_id=target AND (g.actor_id=identity.current_actor() OR EXISTS(SELECT 1
 FROM identity.tenant_memberships m WHERE m.tenant_id=u.tenant_id AND m.user_id=identity.current_actor()
 AND m.role IN ('approver','auditor')));
 IF NOT FOUND THEN RETURN NULL; END IF;
 SELECT COALESCE(sum(input_tokens),0) AS input,COALESCE(sum(output_tokens),0) AS output,
 COALESCE(sum(cached_tokens),0) AS cached, count(*) FILTER(WHERE cached_tokens IS NULL) AS unknown_cached,COALESCE(sum(held_tokens),0) AS held,
 count(*) FILTER(WHERE status<>'known') AS unknown,
 count(*) FILTER(WHERE known_cost IS NULL) AS unpriced,
 COALESCE(sum(known_cost),0) AS known_cost,COALESCE(sum(held_cost),0) AS held_cost,
 COALESCE(sum(duration_ms),0)/1000.0 AS active,
 array_agg(DISTINCT price->>'version') FILTER(WHERE price IS NOT NULL) AS versions
 INTO a FROM workflow.provider_attempts WHERE tenant_id=r.tenant_id AND run_id=target;
 base_unknown=COALESCE((r.base_usage->>'unknown_usage_count')::int,0);
 RETURN jsonb_build_object('limits',r.limits,'read_attempts',r.reads,'rounds',r.rounds,
 'llm_attempts',r.llm,'input_tokens',a.input+COALESCE((r.base_usage->>'input_tokens')::int,0),
 'output_tokens',a.output+COALESCE((r.base_usage->>'output_tokens')::int,0),
 'cached_input_tokens',CASE WHEN a.unknown_cached>0 OR base_unknown>0 THEN NULL ELSE a.cached END,'reserved_tokens',a.held+CASE WHEN base_unknown>0 THEN
 (r.limits->>'tokens')::int ELSE 0 END,'unknown_usage_count',a.unknown+base_unknown,
 'active_seconds',GREATEST(r.active_seconds,a.active),'reserved_verify_reads',0,
 'known_spend_usd',a.known_cost,'reserved_spend_usd',a.held_cost,
 'cost_status',CASE WHEN a.unknown+base_unknown>0 OR a.unpriced>0 OR r.base_usage ? 'llm_attempts'
 THEN 'partial' ELSE 'known' END,'price_versions',COALESCE(to_jsonb(a.versions),'[]'::jsonb),
 'currency','USD');
END $$;
CREATE FUNCTION workflow.reserve_resource(target uuid, kind text, identity_id uuid,
 requested_model text, reserve_tokens integer, timeout_ms integer) RETURNS boolean
 LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE r record; p record; price_row record; price_doc jsonb; snapshot jsonb; tokens bigint;
 cost numeric=0; aggregates record; period timestamptz=clock_timestamp()-interval '1 hour';
BEGIN
 PERFORM workflow.check_fence(target);
 IF NOT identity.lock_role(identity.current_actor(),identity.current_tenant(),'operator') THEN RETURN false; END IF;
 IF kind NOT IN ('read','round','llm') OR reserve_tokens NOT BETWEEN 0 AND 30000
 OR timeout_ms NOT BETWEEN 0 AND 30000 OR requested_model IS NULL OR length(requested_model)>200
 THEN RETURN false; END IF;
 PERFORM pg_advisory_xact_lock(1801202615);
 SELECT u.* INTO r FROM workflow.usage_reservations u JOIN workflow.agent_runs g
 ON g.tenant_id=u.tenant_id AND g.id=u.run_id WHERE u.tenant_id=identity.current_tenant()
 AND u.run_id=target AND u.actor_id=identity.current_actor()
 AND g.status IN ('queued','running','waiting_for_input','waiting_for_approval') FOR UPDATE OF u;
 IF NOT FOUND THEN RETURN false; END IF;
 SELECT * INTO p FROM workflow.resource_policy WHERE id;
 snapshot=workflow.usage_snapshot(target);
 tokens=(snapshot->>'input_tokens')::bigint+(snapshot->>'output_tokens')::bigint+
 (snapshot->>'reserved_tokens')::bigint;
 IF kind='read' THEN
  IF r.reads>=(r.limits->>'reads')::int THEN RETURN false; END IF;
  UPDATE workflow.usage_reservations SET reads=reads+1 WHERE tenant_id=r.tenant_id AND run_id=target;
 ELSIF kind='round' THEN
  IF r.rounds>=(r.limits->>'rounds')::int THEN RETURN false; END IF;
  UPDATE workflow.usage_reservations SET rounds=rounds+1 WHERE tenant_id=r.tenant_id AND run_id=target;
 ELSE
  IF r.llm>=(r.limits->>'llm_attempts')::int OR tokens+reserve_tokens>(r.limits->>'tokens')::int
  OR (snapshot->>'active_seconds')::numeric >=(r.limits->>'active_seconds')::numeric
  OR EXISTS(SELECT 1 FROM workflow.provider_attempts WHERE tenant_id=r.tenant_id AND attempt_id=identity_id)
  THEN RETURN false; END IF;
  SELECT * INTO price_row FROM workflow.model_prices WHERE model=requested_model
   AND effective_at<=clock_timestamp() AND valid_until>clock_timestamp()
   ORDER BY effective_at DESC,version DESC LIMIT 1;
  IF FOUND THEN price_doc=to_jsonb(price_row);cost=reserve_tokens*
   GREATEST(price_row.input_per_million,price_row.output_per_million)/1000000; END IF;
  IF (snapshot->>'known_spend_usd')::numeric+(snapshot->>'reserved_spend_usd')::numeric+cost>p.spend_run
  THEN RETURN false; END IF;
  SELECT count(*) AS attempts,
   count(*) FILTER(WHERE actor_id=r.actor_id) AS actor_attempts,
   count(*) FILTER(WHERE tenant_id=r.tenant_id) AS tenant_attempts,
   COALESCE(sum(COALESCE(input_tokens,0)+COALESCE(output_tokens,0)+held_tokens),0) AS tokens,
   COALESCE(sum(COALESCE(input_tokens,0)+COALESCE(output_tokens,0)+held_tokens) FILTER(WHERE actor_id=r.actor_id),0) AS actor_tokens,
   COALESCE(sum(COALESCE(input_tokens,0)+COALESCE(output_tokens,0)+held_tokens) FILTER(WHERE tenant_id=r.tenant_id),0) AS tenant_tokens,
   COALESCE(sum(COALESCE(known_cost,0)+held_cost),0) AS spend,
   COALESCE(sum(COALESCE(known_cost,0)+held_cost) FILTER(WHERE actor_id=r.actor_id),0) AS actor_spend,
   COALESCE(sum(COALESCE(known_cost,0)+held_cost) FILTER(WHERE tenant_id=r.tenant_id),0) AS tenant_spend
   INTO aggregates FROM workflow.provider_attempts WHERE created_at>=period AND model<>'scripted';
  IF aggregates.attempts>=p.llm_global_hour OR aggregates.actor_attempts>=p.llm_actor_hour
   OR aggregates.tenant_attempts>=p.llm_tenant_hour OR aggregates.tokens+reserve_tokens>p.tokens_global_hour
   OR aggregates.actor_tokens+reserve_tokens>p.tokens_actor_hour
   OR aggregates.tenant_tokens+reserve_tokens>p.tokens_tenant_hour
   OR aggregates.spend+cost>p.spend_global_hour OR aggregates.actor_spend+cost>p.spend_actor_hour
   OR aggregates.tenant_spend+cost>p.spend_tenant_hour THEN RETURN false; END IF;
  INSERT INTO workflow.provider_attempts(tenant_id,run_id,actor_id,attempt_id,epoch,model,
   tokens_reserved,held_tokens,price,held_cost,duration_ms)
  VALUES(r.tenant_id,target,r.actor_id,identity_id,current_setting('app.execution_epoch')::bigint,
   requested_model,reserve_tokens,reserve_tokens,price_doc,cost,timeout_ms);
  UPDATE workflow.usage_reservations SET llm=llm+1 WHERE tenant_id=r.tenant_id AND run_id=target;
 END IF;
 RETURN true;
END $$;
CREATE FUNCTION workflow.settle_provider(target uuid, identity_id uuid, inputs integer,
 outputs integer, cached integer, served text, duration integer, eligible_pricing boolean) RETURNS boolean
 LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE a record; cost numeric; full_usage boolean; matching_price boolean;
BEGIN
 PERFORM workflow.check_fence(target);
 IF inputs<0 OR outputs<0 OR cached<0 OR cached>inputs OR inputs>1000000 OR outputs>1000000
 OR duration NOT BETWEEN 0 AND 120000 THEN RETURN false; END IF;
 PERFORM pg_advisory_xact_lock(1801202615);
 SELECT * INTO a FROM workflow.provider_attempts WHERE tenant_id=identity.current_tenant()
 AND run_id=target AND attempt_id=identity_id AND actor_id=identity.current_actor() FOR UPDATE;
 IF NOT FOUND OR a.status<>'started' OR a.epoch<>current_setting('app.execution_epoch')::bigint
 THEN RETURN false; END IF;
 full_usage=inputs IS NOT NULL AND outputs IS NOT NULL;
 matching_price=eligible_pricing AND a.price IS NOT NULL AND EXISTS(SELECT 1 FROM workflow.model_prices
 WHERE model=served AND version=a.price->>'version'
 AND input_per_million=(a.price->>'input_per_million')::numeric
 AND cached_per_million=(a.price->>'cached_per_million')::numeric
 AND output_per_million=(a.price->>'output_per_million')::numeric);
 IF full_usage AND cached IS NOT NULL AND matching_price THEN
 cost=((inputs-cached)*(a.price->>'input_per_million')::numeric+
 cached*(a.price->>'cached_per_million')::numeric+outputs*(a.price->>'output_per_million')::numeric)/1000000;
 ELSIF full_usage AND inputs=0 AND outputs=0 AND a.model='scripted' THEN cost=0;
 END IF;
 UPDATE workflow.provider_attempts SET input_tokens=inputs,output_tokens=outputs,cached_tokens=cached,
 served_model=left(served,200),duration_ms=duration,standard_pricing=eligible_pricing,
 status=CASE WHEN full_usage THEN 'known' ELSE 'unknown' END,
 held_tokens=CASE WHEN full_usage THEN 0 ELSE GREATEST(0,tokens_reserved-COALESCE(inputs,0)-COALESCE(outputs,0)) END,
 known_cost=cost,held_cost=CASE WHEN cost IS NOT NULL THEN 0 ELSE held_cost END
 WHERE tenant_id=a.tenant_id AND attempt_id=identity_id;
 RETURN true;
END $$;
CREATE FUNCTION workflow.record_active(target uuid, elapsed numeric) RETURNS void
 LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$ BEGIN
 PERFORM workflow.check_fence(target);
 IF elapsed BETWEEN 0 AND 3600 THEN UPDATE workflow.usage_reservations SET
 active_seconds=GREATEST(active_seconds,elapsed) WHERE tenant_id=identity.current_tenant()
 AND run_id=target AND actor_id=identity.current_actor(); END IF;
END $$;
""")
    op.execute("""
CREATE FUNCTION workflow.consume_source_budget() RETURNS boolean
 LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE p record; k text; bound integer; used_count integer;
 period timestamptz=date_trunc('minute',clock_timestamp());
BEGIN
 IF identity.current_tenant() IS NULL OR identity.current_actor() IS NULL THEN RETURN false; END IF;
 SELECT * INTO p FROM workflow.resource_policy WHERE id;
 PERFORM pg_advisory_xact_lock(1801202616);
 FOR k,bound IN SELECT * FROM (VALUES('global',p.source_global_minute),
  ('tenant:'||identity.current_tenant()::text,p.source_tenant_minute),
  ('actor:'||identity.current_actor()::text,p.source_actor_minute)) v LOOP
  SELECT used INTO used_count FROM workflow.source_budgets WHERE scope=k AND bucket=period;
  IF COALESCE(used_count,0)>=bound THEN RETURN false; END IF;
 END LOOP;
 FOR k IN SELECT unnest(ARRAY['global','tenant:'||identity.current_tenant()::text,
  'actor:'||identity.current_actor()::text]) LOOP
  INSERT INTO workflow.source_budgets(scope,bucket,used) VALUES(k,period,1)
  ON CONFLICT(scope,bucket) DO UPDATE SET used=workflow.source_budgets.used+1;
 END LOOP;
 RETURN true;
END $$;
CREATE FUNCTION workflow.cache_source_version() RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER
 SET search_path=pg_catalog AS $$ BEGIN
 INSERT INTO workflow.cache_generations(tenant_id)
 SELECT id FROM identity.tenants WHERE id=identity.current_tenant() ON CONFLICT DO NOTHING;
 RETURN (SELECT jsonb_build_object('namespace',g.namespace,'version',g.generation+
 COALESCE((SELECT sum(o.version) FROM workflow.cache_objects o WHERE o.tenant_id=g.tenant_id),0))
 FROM workflow.cache_generations g WHERE g.tenant_id=identity.current_tenant());
END $$;
CREATE FUNCTION workflow.invalidate_cache() RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER
 SET search_path=pg_catalog AS $$ DECLARE t uuid; key text; BEGIN
 IF TG_OP='UPDATE' AND NEW IS NOT DISTINCT FROM OLD THEN RETURN NEW; END IF;
 t=COALESCE(NEW.tenant_id,OLD.tenant_id);
 key=TG_TABLE_NAME||':'||COALESCE(to_jsonb(NEW)->>'id',to_jsonb(NEW)->>'integration_id',
 to_jsonb(OLD)->>'id',to_jsonb(OLD)->>'integration_id');
 INSERT INTO workflow.cache_objects(tenant_id,object_key) VALUES(t,key)
 ON CONFLICT(tenant_id,object_key) DO UPDATE SET version=workflow.cache_objects.version+1;
 IF TG_OP='UPDATE' AND OLD.tenant_id IS DISTINCT FROM NEW.tenant_id THEN
 INSERT INTO workflow.cache_objects(tenant_id,object_key) VALUES(OLD.tenant_id,key)
 ON CONFLICT(tenant_id,object_key) DO UPDATE SET version=workflow.cache_objects.version+1;
 END IF;
 RETURN COALESCE(NEW,OLD); END $$;
CREATE FUNCTION workflow.worker_slot(target uuid, enforce_fair boolean, servable uuid[]) RETURNS boolean
 LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE p record; actor uuid; tenant uuid=identity.current_tenant(); next_tenant uuid;
BEGIN
 IF array_length(servable,1) NOT BETWEEN 1 AND 64 OR NOT tenant=ANY(servable) THEN RETURN false; END IF;
 PERFORM pg_advisory_xact_lock(1801202617);
 SELECT actor_id INTO actor FROM workflow.agent_runs WHERE tenant_id=tenant AND id=target;
 IF actor IS NULL THEN RETURN false; END IF;
 SELECT * INTO p FROM workflow.resource_policy WHERE id;
 IF (SELECT count(*) FROM workflow.run_execution_leases WHERE owner IS NOT NULL
 AND lease_until>clock_timestamp())>=p.worker_global
 OR (SELECT count(*) FROM workflow.run_execution_leases WHERE tenant_id=tenant AND owner IS NOT NULL
 AND lease_until>clock_timestamp())>=p.worker_tenant
 OR (SELECT count(*) FROM workflow.run_execution_leases l JOIN workflow.agent_runs r
 ON r.tenant_id=l.tenant_id AND r.id=l.run_id WHERE r.actor_id=actor AND l.owner IS NOT NULL
 AND l.lease_until>clock_timestamp())>=p.worker_actor THEN RETURN false; END IF;
 IF enforce_fair THEN
 SELECT j.tenant_id INTO next_tenant FROM workflow.command_jobs j
 LEFT JOIN workflow.worker_admission w ON w.tenant_id=j.tenant_id
 WHERE j.tenant_id=ANY(servable) AND j.status='pending' AND j.available_at<=clock_timestamp()
 AND NOT EXISTS(SELECT 1 FROM workflow.run_execution_leases l WHERE l.tenant_id=j.tenant_id
 AND l.run_id=j.run_id AND l.owner IS NOT NULL AND l.lease_until>clock_timestamp())
 AND (SELECT count(*) FROM workflow.run_execution_leases l WHERE l.tenant_id=j.tenant_id
 AND l.owner IS NOT NULL AND l.lease_until>clock_timestamp())<p.worker_tenant
 AND (SELECT count(*) FROM workflow.run_execution_leases l JOIN workflow.agent_runs r
 ON r.tenant_id=l.tenant_id AND r.id=l.run_id WHERE r.actor_id=(SELECT g.actor_id
 FROM workflow.agent_runs g WHERE g.tenant_id=j.tenant_id AND g.id=j.run_id)
 AND l.owner IS NOT NULL AND l.lease_until>clock_timestamp())<p.worker_actor
 ORDER BY COALESCE(w.admitted_at,'-infinity'::timestamptz),j.created_at,j.id LIMIT 1;
 IF next_tenant IS DISTINCT FROM tenant THEN RETURN false; END IF;
 END IF;
 INSERT INTO workflow.worker_admission(tenant_id,admitted_at) VALUES(tenant,clock_timestamp())
 ON CONFLICT(tenant_id) DO UPDATE SET admitted_at=EXCLUDED.admitted_at;
 RETURN true;
END $$;
""")
    for table in ("customers", "customer_integrations", "incidents", "knowledge_articles", "connector_controls"):
        op.execute(f"""CREATE TRIGGER cache_invalidation AFTER INSERT OR UPDATE OR DELETE ON domain.{table}
 FOR EACH ROW EXECUTE FUNCTION workflow.invalidate_cache()""")
    functions = {
        "init_usage()": "",
        "usage_snapshot(uuid)": "ops_workflow",
        "reserve_resource(uuid,text,uuid,text,integer,integer)": "ops_workflow",
        "settle_provider(uuid,uuid,integer,integer,integer,text,integer,boolean)": "ops_workflow",
        "record_active(uuid,numeric)": "ops_workflow",
        "consume_source_budget()": "ops_domain",
        "cache_source_version()": "ops_domain",
        "invalidate_cache()": "",
        "worker_slot(uuid,boolean,uuid[])": "ops_workflow",
    }
    for signature, role in functions.items():
        op.execute(f"REVOKE ALL ON FUNCTION workflow.{signature} FROM PUBLIC")
        if role:
            op.execute(f"GRANT EXECUTE ON FUNCTION workflow.{signature} TO {role}")


def downgrade() -> None:
    raise RuntimeError("Preserve durable usage; restore an isolated Full backup")

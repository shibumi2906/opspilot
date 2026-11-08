"""Separate worker admission serialization from lifecycle maintenance exclusion.

Every runtime transaction already holds the shared lifecycle lock. Upgrading it
inside worker_slot blocked nested approval/checkpoint readers behind a queued
exclusive waiter. Keep maintenance shared, serialize admission on its own key.
"""

from alembic import op

revision = "0021_worker_admission"
down_revision = "0020_prometheus"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
DO $migration$
DECLARE definition text;
 old_lock text = 'PERFORM pg_advisory_xact_lock(1801202617);';
 new_lock text = 'PERFORM pg_advisory_xact_lock(1801202621);';
BEGIN
 SELECT pg_get_functiondef('workflow.worker_slot(uuid,boolean,uuid[])'::regprocedure)
 INTO definition;
 IF (length(definition)-length(replace(definition,old_lock,'')))<>length(old_lock)
 THEN RAISE EXCEPTION 'UNEXPECTED_WORKER_ADMISSION_CONTRACT'; END IF;
 EXECUTE replace(definition,old_lock,new_lock);
END $migration$;
""")


def downgrade() -> None:
    raise RuntimeError("Do not restore the admission/maintenance lock inversion")

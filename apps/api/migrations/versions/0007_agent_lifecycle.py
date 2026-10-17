"""One active draft, snapshot lineage, retained discards and admin retirement."""

import sqlalchemy as sa
from alembic import op

revision = "0007_agent_lifecycle"
down_revision = "0006_private_access_tokens"
branch_labels = None
depends_on = None

# Preserve all previous snapshot, model, policy and tool checks. Only a validated
# discard bypasses approval checks, so revoked dependencies do not trap a draft.
VERSION_GUARD = """
CREATE OR REPLACE FUNCTION guard_agent_version() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP IN ('UPDATE','DELETE') AND OLD.status='snapshot' THEN
    RAISE EXCEPTION 'Immutable snapshot' USING ERRCODE='23514';
  END IF;
  IF TG_OP='DELETE' THEN RETURN OLD; END IF;
  IF TG_OP='INSERT' AND NEW.status<>'draft' THEN
    RAISE EXCEPTION 'Versions must start as drafts' USING ERRCODE='23514';
  END IF;
  IF TG_OP='UPDATE' AND ROW(NEW.agent_id,NEW.number,NEW.created_by,NEW.source_version)
    IS DISTINCT FROM ROW(OLD.agent_id,OLD.number,OLD.created_by,OLD.source_version) THEN
    RAISE EXCEPTION 'Immutable version identity' USING ERRCODE='23514';
  END IF;
  -- DISCARD_POLICY
  PERFORM id FROM models WHERE id=NEW.model_id AND status='approved' FOR SHARE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'Model must be approved' USING ERRCODE='23514';
  END IF;
  IF NEW.configuration #>> '{model,model_id}' IS DISTINCT FROM NEW.model_id OR
     NEW.configuration->'security' IS DISTINCT FROM
     '{"require_authentication": true,"resource_scope": "caller_owned",
       "allow_financial_writes": false}'::jsonb THEN
    RAISE EXCEPTION 'Invalid model reference or policy' USING ERRCODE='23514';
  END IF;
  IF NEW.status='snapshot' THEN
    IF NEW.snapshot->'configuration' IS DISTINCT FROM NEW.configuration THEN
      RAISE EXCEPTION 'Snapshot configuration mismatch' USING ERRCODE='23514';
    END IF;
    IF EXISTS(SELECT 1 FROM agent_tools b JOIN tools t ON t.id=b.tool_id
      JOIN agents a ON a.id=b.agent_id JOIN users u ON u.id=a.owner_id
      WHERE b.agent_id=NEW.agent_id AND b.version_number=NEW.number
      AND (t.status<>'approved' OR t.operation<>'read' OR NOT t.permissions <@ u.permissions)) THEN
      RAISE EXCEPTION 'Tool not approved or authorized' USING ERRCODE='23514';
    END IF;
  END IF;
  RETURN NEW;
END $$;
"""


def upgrade():
    op.add_column("agents", sa.Column("deleted_at", sa.DateTime(timezone=True)))
    op.create_check_constraint(
        op.f("ck_agents_deleted_state"), "agents", "deleted_at IS NULL OR status='deprecated'"
    )
    op.add_column("agent_versions", sa.Column("discarded_at", sa.DateTime(timezone=True)))
    op.add_column("agent_versions", sa.Column("discard_reason", sa.String(80)))
    op.drop_constraint(op.f("ck_agent_versions_status"), "agent_versions", type_="check")
    op.drop_constraint(op.f("ck_agent_versions_snapshot_state"), "agent_versions", type_="check")
    op.create_check_constraint(
        op.f("ck_agent_versions_status"),
        "agent_versions",
        "status IN ('draft','snapshot','discarded')",
    )
    op.create_check_constraint(
        op.f("ck_agent_versions_snapshot_state"),
        "agent_versions",
        """
      (status IN ('draft','discarded') AND snapshot IS NULL AND config_hash IS NULL) OR
      (status='snapshot' AND jsonb_typeof(snapshot)='object' AND snapshot IS NOT NULL
       AND config_hash IS NOT NULL AND config_hash ~ '^[a-f0-9]{64}$')
    """,
    )
    op.create_check_constraint(
        op.f("ck_agent_versions_discard_state"),
        "agent_versions",
        """
      (status='discarded' AND discarded_at IS NOT NULL AND discard_reason IS NOT NULL) OR
      (status<>'discarded' AND discarded_at IS NULL AND discard_reason IS NULL)
    """,
    )
    op.execute(
        VERSION_GUARD.replace(
            "-- DISCARD_POLICY",
            "IF TG_OP='UPDATE' AND OLD.status='draft' AND NEW.status='discarded' "
            "THEN RETURN NEW; END IF;",
        )
    )
    # Keep every historical row and all immutable snapshots/hashes. Explicitly
    # identify migration discards instead of attributing them to a human actor.
    op.execute("""
      UPDATE agent_versions v SET status='discarded', discarded_at=now(),
        discard_reason='legacy_superseded_draft', revision=revision+1
      WHERE v.status='draft' AND (
        v.number < (SELECT max(d.number) FROM agent_versions d
                    WHERE d.agent_id=v.agent_id AND d.status='draft')
        OR v.number < COALESCE((SELECT max(s.number) FROM agent_versions s
                                WHERE s.agent_id=v.agent_id AND s.status='snapshot'),0)
      )
    """)
    op.execute("SET CONSTRAINTS ALL IMMEDIATE")
    op.create_index(
        "uq_agent_versions_active_draft",
        "agent_versions",
        ["agent_id"],
        unique=True,
        postgresql_where=sa.text("status = 'draft'"),
    )
    op.execute("""
    CREATE FUNCTION guard_agent_lifecycle() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE parent agents%ROWTYPE;
    BEGIN
      IF TG_OP='DELETE' THEN
        RAISE EXCEPTION 'Version history must be retained' USING ERRCODE='23514';
      END IF;
      SELECT * INTO parent FROM agents WHERE id=NEW.agent_id FOR UPDATE;
      IF TG_OP='UPDATE' AND OLD.status='discarded' THEN
        RAISE EXCEPTION 'Discarded versions are immutable' USING ERRCODE='23514';
      END IF;
      IF TG_OP='UPDATE' AND NEW.status='discarded' THEN
        IF OLD.status<>'draft' OR NEW.revision<>OLD.revision+1 OR
          (to_jsonb(NEW)-ARRAY['status','revision','discarded_at','discard_reason'])
          IS DISTINCT FROM
          (to_jsonb(OLD)-ARRAY['status','revision','discarded_at','discard_reason']) THEN
          RAISE EXCEPTION 'Discard must preserve draft contents' USING ERRCODE='23514';
        END IF;
        IF parent.deleted_at IS NULL AND NOT EXISTS(SELECT 1 FROM agent_versions
          WHERE agent_id=NEW.agent_id AND status='snapshot' AND number<NEW.number) THEN
          RAISE EXCEPTION 'Initial draft cannot be discarded' USING ERRCODE='23514';
        END IF;
        RETURN NEW;
      END IF;
      IF parent.deleted_at IS NOT NULL OR parent.status<>'draft' THEN
        RAISE EXCEPTION 'Agent is not editable' USING ERRCODE='23514';
      END IF;
      IF TG_OP='INSERT' THEN
        IF EXISTS(SELECT 1 FROM agent_versions WHERE agent_id=NEW.agent_id AND status='draft') THEN
          RAISE EXCEPTION 'An active draft already exists' USING ERRCODE='23514';
        END IF;
        IF EXISTS(SELECT 1 FROM agent_versions WHERE agent_id=NEW.agent_id) THEN
          IF NOT EXISTS(SELECT 1 FROM agent_versions WHERE agent_id=NEW.agent_id
                        AND number=NEW.source_version AND status='snapshot') THEN
            RAISE EXCEPTION 'Source must be a frozen snapshot' USING ERRCODE='23514';
          END IF;
        ELSIF NEW.source_version IS NOT NULL THEN
          RAISE EXCEPTION 'Initial draft has no source' USING ERRCODE='23514';
        END IF;
      END IF;
      RETURN NEW;
    END $$;
    CREATE TRIGGER guard_lifecycle BEFORE INSERT OR UPDATE OR DELETE ON agent_versions
      FOR EACH ROW EXECUTE FUNCTION guard_agent_lifecycle();
    CREATE FUNCTION guard_deleted_agent() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      IF OLD.deleted_at IS NOT NULL THEN
        RAISE EXCEPTION 'Deleted agents are immutable' USING ERRCODE='23514';
      END IF;
      IF NEW.deleted_at IS NOT NULL AND EXISTS(
          SELECT 1 FROM agent_versions WHERE agent_id=OLD.id AND status='snapshot') THEN
        RAISE EXCEPTION 'Agents with snapshots cannot be deleted' USING ERRCODE='23514';
      END IF;
      RETURN NEW;
    END $$;
    CREATE TRIGGER guard_deleted_agent BEFORE UPDATE ON agents
      FOR EACH ROW EXECUTE FUNCTION guard_deleted_agent();
    """)


def downgrade():
    op.execute("DROP TRIGGER guard_lifecycle ON agent_versions")
    op.execute("DROP FUNCTION guard_agent_lifecycle()")
    op.execute("DROP TRIGGER guard_deleted_agent ON agents")
    op.execute("DROP FUNCTION guard_deleted_agent()")
    op.drop_index("uq_agent_versions_active_draft", table_name="agent_versions")
    # Returning to the old schema restores its multiple-draft semantics. No
    # snapshot, configuration, hash, relation or audit event is changed.
    op.execute(
        VERSION_GUARD.replace(
            "-- DISCARD_POLICY",
            "IF TG_OP='UPDATE' AND OLD.status='discarded' AND NEW.status='draft' "
            "THEN RETURN NEW; END IF;",
        )
    )
    op.execute(
        "UPDATE agent_versions SET status='draft',discarded_at=NULL,discard_reason=NULL "
        "WHERE status='discarded'"
    )
    op.execute("SET CONSTRAINTS ALL IMMEDIATE")
    op.execute(VERSION_GUARD.replace("-- DISCARD_POLICY", ""))
    for name in ("discard_state", "snapshot_state", "status"):
        op.drop_constraint(op.f(f"ck_agent_versions_{name}"), "agent_versions", type_="check")
    op.create_check_constraint(
        op.f("ck_agent_versions_status"), "agent_versions", "status IN ('draft','snapshot')"
    )
    op.create_check_constraint(
        op.f("ck_agent_versions_snapshot_state"),
        "agent_versions",
        """
      (status='draft' AND snapshot IS NULL AND config_hash IS NULL) OR
      (status='snapshot' AND jsonb_typeof(snapshot)='object' AND snapshot IS NOT NULL
       AND config_hash IS NOT NULL AND config_hash ~ '^[a-f0-9]{64}$')
    """,
    )
    op.drop_column("agent_versions", "discard_reason")
    op.drop_column("agent_versions", "discarded_at")
    op.drop_constraint(op.f("ck_agents_deleted_state"), "agents", type_="check")
    op.drop_column("agents", "deleted_at")

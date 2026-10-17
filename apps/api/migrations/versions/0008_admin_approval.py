"""Allow audited administrator self-decisions; keep independent approvers."""

from alembic import op

revision = "0008_admin_approval"
down_revision = "0007_agent_lifecycle"
branch_labels = None
depends_on = None

GUARD = """
CREATE OR REPLACE FUNCTION guard_approval() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP='DELETE' OR (TG_OP='UPDATE' AND OLD.status<>'pending') THEN
    RAISE EXCEPTION 'Decided approvals are immutable' USING ERRCODE='23514';
  END IF;
  IF TG_OP='UPDATE' AND (to_jsonb(NEW)-ARRAY['status','decided_by','decided_at','reason'])
    IS DISTINCT FROM (to_jsonb(OLD)-ARRAY['status','decided_by','decided_at','reason']) THEN
    RAISE EXCEPTION 'Immutable approval identity' USING ERRCODE='23514';
  END IF;
  IF TG_OP='INSERT' AND NEW.status<>'pending' THEN
    RAISE EXCEPTION 'Approval must start pending' USING ERRCODE='23514';
  END IF;
  -- REASON_POLICY
  IF NOT EXISTS(SELECT 1 FROM evaluation_runs e JOIN agent_versions v
    ON v.agent_id=e.agent_id AND v.number=e.version_number
    WHERE e.id=NEW.evaluation_id AND e.agent_id=NEW.agent_id AND e.version_number=NEW.version_number
    AND e.config_hash=NEW.config_hash AND v.config_hash=NEW.config_hash
    AND e.status='passed' AND e.critical_failures=0) THEN
    RAISE EXCEPTION 'Approval requires passing evaluation of the exact hash' USING ERRCODE='23514';
  END IF;
  IF NEW.status<>'pending' AND NOT EXISTS(SELECT 1 FROM users u JOIN agents a ON a.id=NEW.agent_id
    JOIN agent_versions v ON v.agent_id=a.id AND v.number=NEW.version_number
    WHERE u.id=NEW.decided_by AND u.active AND -- DECISION_POLICY
  ) THEN
    RAISE EXCEPTION 'Authorized decision maker required' USING ERRCODE='23514';
  END IF;
  RETURN NEW;
END $$;
"""

INDEPENDENT = "u.id<>NEW.requested_by AND u.id<>a.owner_id AND u.id<>v.created_by"
DECISION = (
    "(status = 'pending' AND decided_by IS NULL AND decided_at IS NULL) OR "
    "(status <> 'pending' AND decided_by IS NOT NULL AND decided_at IS NOT NULL)"
)
OLD_DECISION = DECISION[:-1] + " AND decided_by <> requested_by)"
REASON_POLICY = """
  IF NEW.status<>'pending' AND length(btrim(NEW.reason))=0 THEN
    RAISE EXCEPTION 'A decision reason is required' USING ERRCODE='23514';
  END IF;
"""


def upgrade():
    op.drop_constraint(op.f("ck_approvals_decision"), "approvals", type_="check")
    op.create_check_constraint(op.f("ck_approvals_decision"), "approvals", DECISION)
    op.execute(
        GUARD.replace(
            "-- DECISION_POLICY",
            f"(u.role='administrator' OR (u.role='approver' AND {INDEPENDENT}))",
        ).replace("-- REASON_POLICY", REASON_POLICY)
    )


def downgrade():
    # Restore the previous rule for future decisions. Historical decisions and
    # append-only audit events are preserved, including administrator overrides.
    op.execute(
        GUARD.replace(
            "-- DECISION_POLICY",
            f"u.role IN ('approver','administrator') AND {INDEPENDENT}",
        )
        .replace("-- REASON_POLICY", "")
        .replace("Authorized decision maker required", "Authorized independent approver required")
    )
    op.drop_constraint(op.f("ck_approvals_decision"), "approvals", type_="check")
    # Existing, immutable admin decisions may have decided_by=requested_by.
    # Preserve those rows while applying the old check to all future writes.
    op.execute(
        "ALTER TABLE approvals ADD CONSTRAINT ck_approvals_decision "
        f"CHECK ({OLD_DECISION}) NOT VALID"
    )

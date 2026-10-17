from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.agents.models import Agent, AgentVersion
from app.agents.service import check_revision, configuration_hash, fail, get_agent, get_version
from app.governance.audit import record
from app.governance.models import (
    Approval,
    EvaluationSuite,
    Publication,
    VersionGovernance,
)
from app.governance.policy import gate
from app.governance.schemas import (
    DecisionRequest,
    GovernanceAction,
    GovernanceRead,
    InvocationRequest,
    PublishRequest,
    RollbackRequest,
    SuiteCreate,
)
from app.identity.models import User
from app.runtime.models import InvocationGrant

STAFF = frozenset({"administrator", "reviewer", "approver", "auditor"})


def require_role(user: User, roles: set[str]) -> None:
    if user.role not in roles:
        fail(403, "FORBIDDEN", "This operation requires an authorized governance role")


def own_or_staff(session: Session, agent_id: str, user: User) -> Agent:
    agent = get_agent(session, agent_id, user)
    if agent.owner_id != user.id and user.role not in STAFF:
        fail(404, "NOT_FOUND", "Governance record not found")
    return agent


def editable_owner(session: Session, agent_id: str, user: User) -> Agent:
    agent = get_agent(session, agent_id, user, edit=True)
    if agent.status != "draft":
        fail(409, "AGENT_DISABLED", "Agent must be enabled")
    return agent


def lifecycle(
    session: Session, agent_id: str, number: int
) -> tuple[AgentVersion, VersionGovernance]:
    version = get_version(session, agent_id, number)
    if version.status != "snapshot":
        fail(409, "SNAPSHOT_REQUIRED", "Freeze the configuration before evaluation or approval")
    item = session.get(VersionGovernance, (agent_id, number))
    if item is None:
        item = VersionGovernance(
            agent_id=agent_id, version_number=number, config_hash=version.config_hash
        )
        session.add(item)
        session.flush()
    return version, item


def check_action(item: VersionGovernance, data: GovernanceAction) -> None:
    check_revision(item.revision, data.expected_revision)
    if item.config_hash != data.expected_config_hash:
        fail(409, "CONFIG_HASH_MISMATCH", "Reload the exact version hash")


def require_gate(session: Session, version: AgentVersion, *, approval=False):
    result = gate(session, version, require_approval=approval)
    if not result.eligible:
        fail(409, "PUBLICATION_GATE_BLOCKED", ", ".join(result.reasons))
    return result


def create_suite(session: Session, data: SuiteCreate, user: User) -> EvaluationSuite:
    require_role(user, {"administrator", "reviewer"})
    item = EvaluationSuite(
        **data.model_dump(),
        suite_hash=configuration_hash(data.model_dump(mode="json")),
        created_by=user.id,
    )
    session.add(item)
    record(
        session,
        user.id,
        "suite.created",
        suite_id=data.id,
        suite_version=data.version,
        suite_hash=item.suite_hash,
    )
    session.commit()
    return item


def info(session: Session, agent_id: str, number: int, user: User) -> GovernanceRead:
    own_or_staff(session, agent_id, user)
    version = get_version(session, agent_id, number)
    item = session.get(VersionGovernance, (agent_id, number))
    publication = session.get(Publication, agent_id)
    return GovernanceRead(
        agent_id=agent_id,
        version_number=number,
        config_hash=version.config_hash or "",
        stage=item.stage if item else "draft",
        revision=item.revision if item else 1,
        latest_evaluation_id=item.latest_evaluation_id if item else None,
        approval_id=item.approval_id if item else None,
        ever_published=item.ever_published if item else False,
        publication_version=publication.version_number if publication else None,
        publication_revision=publication.revision if publication else 0,
        publication_enabled=publication.enabled if publication else False,
        gate=gate(session, version, require_approval=True),
    )


def submit(
    session: Session, agent_id: str, number: int, data: GovernanceAction, user: User
) -> Approval:
    editable_owner(session, agent_id, user)
    version, item = lifecycle(session, agent_id, number)
    check_action(item, data)
    if item.stage != "testing":
        fail(409, "INVALID_TRANSITION", "A tested candidate is required before submission")
    outcome = require_gate(session, version)
    approval = Approval(
        id=f"apr-{uuid4().hex}",
        agent_id=agent_id,
        version_number=number,
        evaluation_id=outcome.evaluation_id,
        config_hash=version.config_hash,
        requested_by=user.id,
    )
    session.add(approval)
    session.flush()
    item.approval_id, item.stage = approval.id, "pending_approval"
    item.revision += 1
    record(
        session,
        user.id,
        "approval.requested",
        agent_id,
        number,
        approval_id=approval.id,
        evaluation_id=outcome.evaluation_id,
        config_hash=version.config_hash,
    )
    session.commit()
    return approval


def decide(
    session: Session, agent_id: str, number: int, data: DecisionRequest, user: User
) -> Approval:
    require_role(user, {"administrator", "approver"})
    agent = get_agent(session, agent_id, user)
    session.refresh(agent, with_for_update=True)
    version, item = lifecycle(session, agent_id, number)
    check_action(item, data)
    if agent.status != "draft" or item.stage != "pending_approval" or not item.approval_id:
        fail(409, "INVALID_TRANSITION", "A pending approval is required")
    approval = session.get(Approval, item.approval_id)
    self_decision = user.id in {agent.owner_id, version.created_by, approval.requested_by}
    if user.role != "administrator" and self_decision:
        fail(
            403,
            "SELF_APPROVAL_FORBIDDEN",
            "Approvers cannot decide on a version they authored, own or requested; "
            "an administrator may decide with an audited reason",
        )
    if data.decision == "approved":
        require_gate(session, version)
    approval.status, approval.decided_by, approval.reason, approval.decided_at = (
        data.decision,
        user.id,
        data.reason,
        datetime.now(UTC),
    )
    item.stage = "approved" if data.decision == "approved" else "draft"
    item.revision += 1
    record(
        session,
        user.id,
        f"approval.{data.decision}",
        agent_id,
        number,
        approval_id=approval.id,
        evaluation_id=approval.evaluation_id,
        config_hash=version.config_hash,
        reason=data.reason,
        decision_role=user.role,
        administrator_override=user.role == "administrator" and self_decision,
    )
    session.commit()
    return approval


def activate(
    session: Session,
    agent: Agent,
    version: AgentVersion,
    item: VersionGovernance,
    user: User,
    expected_publication_revision: int,
    *,
    rollback_reason: str | None = None,
) -> Publication:
    require_gate(session, version, approval=True)
    publication = session.get(Publication, agent.id)
    check_revision(publication.revision if publication else 0, expected_publication_revision)
    if publication and publication.enabled and publication.version_number == version.number:
        fail(409, "ALREADY_PUBLISHED", "This version is already active")
    previous = publication.version_number if publication and publication.enabled else None
    if previous is not None:
        old = session.get(VersionGovernance, (agent.id, previous))
        old.stage = "deprecated"
        old.revision += 1
    item.stage, item.ever_published = "published", True
    item.revision += 1
    if publication is None:
        publication = Publication(
            agent_id=agent.id, version_number=version.number, updated_by=user.id
        )
        session.add(publication)
    else:
        publication.version_number, publication.enabled = version.number, True
        publication.revision += 1
        publication.updated_by, publication.updated_at = user.id, datetime.now(UTC)
    # Publication grants only the existing owner invocation, never business-data permissions.
    session.execute(
        insert(InvocationGrant)
        .values(
            agent_id=agent.id, version_number=version.number, user_id=agent.owner_id, enabled=True
        )
        .on_conflict_do_nothing(
            index_elements=[
                InvocationGrant.agent_id,
                InvocationGrant.version_number,
                InvocationGrant.user_id,
            ]
        )
    )
    record(
        session,
        user.id,
        "publication.rollback" if rollback_reason else "version.published",
        agent.id,
        version.number,
        config_hash=version.config_hash,
        previous_version=previous,
        approval_id=item.approval_id,
        evaluation_id=item.latest_evaluation_id,
        reason=rollback_reason,
    )
    session.commit()
    return publication


def publish(
    session: Session, agent_id: str, number: int, data: PublishRequest, user: User
) -> Publication:
    require_role(user, {"administrator", "approver"})
    agent = get_agent(session, agent_id, user)
    session.refresh(agent, with_for_update=True)
    version, item = lifecycle(session, agent_id, number)
    check_action(item, data)
    if agent.status != "draft" or item.stage != "approved" or item.ever_published:
        fail(409, "INVALID_TRANSITION", "Publish requires an approved, unpublished candidate")
    return activate(session, agent, version, item, user, data.expected_publication_revision)


def rollback(session: Session, agent_id: str, data: RollbackRequest, user: User) -> Publication:
    require_role(user, {"administrator", "approver"})
    agent = get_agent(session, agent_id, user)
    session.refresh(agent, with_for_update=True)
    version, item = lifecycle(session, agent_id, data.target_version)
    if (
        agent.status != "draft"
        or not item.ever_published
        or item.stage not in {"deprecated", "disabled"}
    ):
        fail(
            409,
            "ROLLBACK_TARGET_INVALID",
            "Rollback requires a previously published and approved version",
        )
    return activate(
        session,
        agent,
        version,
        item,
        user,
        data.expected_publication_revision,
        rollback_reason=data.reason,
    )


def disable(
    session: Session, agent_id: str, number: int, data: GovernanceAction, user: User
) -> None:
    require_role(user, {"administrator", "approver"})
    agent = get_agent(session, agent_id, user)
    session.refresh(agent, with_for_update=True)
    _, item = lifecycle(session, agent_id, number)
    check_action(item, data)
    if item.stage not in {"approved", "published", "deprecated"}:
        fail(409, "INVALID_TRANSITION", "Only an approved release can be disabled")
    item.stage = "disabled"
    item.revision += 1
    publication = session.get(Publication, agent_id)
    if publication and publication.version_number == number:
        publication.enabled = False
        publication.revision += 1
        publication.updated_by, publication.updated_at = user.id, datetime.now(UTC)
    record(session, user.id, "version.disabled", agent_id, number, config_hash=item.config_hash)
    session.commit()


def grant_invocation(
    session: Session, agent_id: str, number: int, data: InvocationRequest, user: User
) -> None:
    require_role(user, {"administrator"})
    agent = get_agent(session, agent_id, user)
    session.refresh(agent, with_for_update=True)
    version = get_version(session, agent_id, number)
    principal = session.get(User, data.user_id)
    if (
        version.status != "snapshot"
        or principal is None
        or not principal.active
        or principal.id.startswith("evaluation-")
    ):
        fail(422, "INVALID_GRANT", "Select an active user and a frozen version")
    session.execute(
        insert(InvocationGrant)
        .values(
            agent_id=agent_id, version_number=number, user_id=principal.id, enabled=data.enabled
        )
        .on_conflict_do_update(
            index_elements=[
                InvocationGrant.agent_id,
                InvocationGrant.version_number,
                InvocationGrant.user_id,
            ],
            set_={"enabled": data.enabled},
        )
    )
    record(
        session,
        user.id,
        "invocation.granted" if data.enabled else "invocation.revoked",
        agent_id,
        number,
        user_id=principal.id,
        reason=data.reason,
    )
    session.commit()

"""Trace visibility and aggregates over persisted observations, never synthetic estimates."""

from sqlalchemy import and_, exists, func, or_, select
from sqlalchemy.orm import Session

from app.agents.models import Agent
from app.governance.models import EvaluationRun
from app.identity.models import User
from app.runtime.models import AgentRun, ToolCall


def visibility(user: User):
    if user.role == "auditor":
        return True
    evaluation = exists(
        select(EvaluationRun.id)
        .join(Agent, Agent.id == EvaluationRun.agent_id)
        .where(
            EvaluationRun.id == AgentRun.evaluation_id,
            True
            if user.role in {"administrator", "reviewer", "approver"}
            else Agent.owner_id == user.id,
        )
    )
    return or_(AgentRun.caller_id == user.id, and_(AgentRun.channel == "evaluation", evaluation))


def metrics(session: Session, user: User) -> dict:
    visible = select(AgentRun).where(visibility(user), AgentRun.channel != "evaluation").subquery()
    latency = func.extract("epoch", visible.c.completed_at - visible.c.started_at) * 1000
    row = (
        session.execute(
            select(
                func.count().label("runs"),
                func.count().filter(visible.c.status == "completed").label("completed"),
                func.count().filter(visible.c.status == "failed").label("failed"),
                func.count().filter(visible.c.status == "denied").label("denied"),
                func.count().filter(visible.c.status == "escalated").label("escalated"),
                func.count().filter(visible.c.status == "running").label("running"),
                func.avg(latency).label("latency_avg_ms"),
                func.percentile_cont(0.5).within_group(latency).label("latency_p50_ms"),
                func.percentile_cont(0.95).within_group(latency).label("latency_p95_ms"),
            )
        )
        .mappings()
        .one()
    )
    models = (
        session.execute(
            select(
                visible.c.model_id,
                visible.c.mode,
                func.count().label("runs"),
                func.sum(visible.c.input_tokens).label("input_tokens"),
                func.count(visible.c.input_tokens).label("input_tokens_known_runs"),
                func.sum(visible.c.output_tokens).label("output_tokens"),
                func.count(visible.c.output_tokens).label("output_tokens_known_runs"),
                func.sum(visible.c.estimated_cost_usd).label("estimated_cost_usd"),
                func.count(visible.c.estimated_cost_usd).label("cost_known_runs"),
            )
            .group_by(visible.c.model_id, visible.c.mode)
            .order_by(visible.c.model_id, visible.c.mode)
        )
        .mappings()
        .all()
    )
    calls = session.execute(
        select(func.count(), func.count().filter(ToolCall.status != "completed")).join(
            visible, visible.c.id == ToolCall.run_id
        )
    ).one()
    return {
        **dict(row),
        "tool_calls": calls[0],
        "tool_errors": calls[1],
        "models": [
            {
                **dict(r),
                "estimated_cost_usd": str(r["estimated_cost_usd"])
                if r["estimated_cost_usd"] is not None
                else None,
            }
            for r in models
        ],
        "scope": "all runs" if user.role == "auditor" else "own runs",
        "evaluation_runs_excluded": True,
        "cost_kind": "estimate_from_reported_usage_and_catalog_prices",
        "missing_values": "null = unavailable; sums cover only known runs",
    }

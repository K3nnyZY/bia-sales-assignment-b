from dataclasses import dataclass, field
from time import monotonic

from sqlalchemy.orm import Session

from app.agents.schemas import AgentConfiguration
from app.core.config import Settings
from app.runtime.models import AgentRun


@dataclass
class ExecutionContext:
    # Trusted server context, never accepted from a request or persisted as graph state.
    session: Session
    settings: Settings
    run: AgentRun
    caller_id: str
    config: AgentConfiguration
    snapshot: dict
    deadline: float
    steps: int = 0
    tool_count: int = 0
    input_tokens: int | None = None
    output_tokens: int | None = None
    estimated_cost_usd: str | None = None
    node_names: list[str] = field(default_factory=list)

    def remaining_seconds(self) -> float:
        return max(0.001, self.deadline - monotonic())

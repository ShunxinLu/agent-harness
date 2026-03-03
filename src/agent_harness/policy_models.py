"""Policy decision/result data models."""

from pydantic import BaseModel, Field


class PolicyDecision(BaseModel):
    """Single policy decision outcome."""

    action: str
    allowed: bool
    reason: str
    metadata: dict = Field(default_factory=dict)


class PolicyResult(BaseModel):
    """Aggregate policy evaluation result."""

    allowed: bool
    decisions: list[PolicyDecision] = Field(default_factory=list)


"""ModelHostileReviewerPhaseEvent — emitted on each hostile reviewer phase transition."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from omnimarket.nodes.node_hostile_reviewer.models.model_hostile_reviewer_state import (
    EnumHostileReviewerPhase,
)


class ModelHostileReviewerPhaseEvent(BaseModel):
    """Emitted when the hostile reviewer transitions between phases."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    correlation_id: UUID = Field(...)
    from_phase: EnumHostileReviewerPhase = Field(...)
    to_phase: EnumHostileReviewerPhase = Field(...)
    success: bool = Field(...)
    timestamp: datetime = Field(...)
    error_message: str | None = Field(default=None)


__all__: list[str] = ["ModelHostileReviewerPhaseEvent"]

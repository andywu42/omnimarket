"""ModelPipelinePhaseEvent — emitted on each pipeline phase transition."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from omnimarket.nodes.node_ticket_pipeline.models.model_pipeline_state import (
    EnumPipelinePhase,
)


class ModelPipelinePhaseEvent(BaseModel):
    """Emitted when the ticket pipeline transitions between phases."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    correlation_id: UUID = Field(...)
    ticket_id: str = Field(...)
    from_phase: EnumPipelinePhase = Field(...)
    to_phase: EnumPipelinePhase = Field(...)
    success: bool = Field(...)
    timestamp: datetime = Field(...)
    error_message: str | None = Field(default=None)


__all__: list[str] = ["ModelPipelinePhaseEvent"]

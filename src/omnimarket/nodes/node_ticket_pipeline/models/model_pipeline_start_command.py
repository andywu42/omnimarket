"""ModelPipelineStartCommand — command to start the ticket pipeline."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ModelPipelineStartCommand(BaseModel):
    """Command to start the ticket pipeline for a given ticket."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    correlation_id: UUID = Field(..., description="Pipeline run correlation ID.")
    ticket_id: str = Field(..., description="Linear ticket ID (e.g. OMN-1234).")
    skip_test_iterate: bool = Field(default=False)
    dry_run: bool = Field(default=False)
    skip_to: str | None = Field(
        default=None, description="Resume from specified phase."
    )
    requested_at: datetime = Field(..., description="When the command was issued.")


__all__: list[str] = ["ModelPipelineStartCommand"]

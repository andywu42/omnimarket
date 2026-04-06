"""ModelPrPolishStartCommand — command to start PR polish."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ModelPrPolishStartCommand(BaseModel):
    """Command to start PR polish."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    correlation_id: UUID = Field(..., description="Polish run correlation ID.")
    pr_number: int | None = Field(default=None, description="PR number.")
    skip_conflicts: bool = Field(default=False)
    dry_run: bool = Field(default=False)
    requested_at: datetime = Field(..., description="When the command was issued.")


__all__: list[str] = ["ModelPrPolishStartCommand"]

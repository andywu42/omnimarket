"""ModelDodVerifyStartCommand — command to start DoD verification."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ModelDodVerifyStartCommand(BaseModel):
    """Command to start DoD evidence verification."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    correlation_id: UUID = Field(..., description="Verification run correlation ID.")
    ticket_id: str = Field(..., description="Linear ticket ID (e.g. OMN-1234).")
    contract_path: str | None = Field(
        default=None, description="Override path to contract YAML."
    )
    dry_run: bool = Field(default=False)
    requested_at: datetime = Field(..., description="When the command was issued.")


__all__: list[str] = ["ModelDodVerifyStartCommand"]

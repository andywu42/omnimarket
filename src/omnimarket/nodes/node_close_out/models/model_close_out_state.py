"""ModelCloseOutState and EnumCloseOutPhase for the close-out pipeline FSM."""

from __future__ import annotations

from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class EnumCloseOutPhase(StrEnum):
    """FSM phases for the close-out pipeline.

    Phase Transitions:
        IDLE -> MERGE_SWEEP -> DEPLOY_PLUGIN -> START_ENV -> INTEGRATION
        -> RELEASE_CHECK -> REDEPLOY_CHECK -> DASHBOARD_SWEEP -> DONE
        Any -> FAILED: Circuit breaker tripped or unrecoverable error
    """

    IDLE = "idle"
    MERGE_SWEEP = "merge_sweep"
    DEPLOY_PLUGIN = "deploy_plugin"
    START_ENV = "start_env"
    INTEGRATION = "integration"
    RELEASE_CHECK = "release_check"
    REDEPLOY_CHECK = "redeploy_check"
    DASHBOARD_SWEEP = "dashboard_sweep"
    DONE = "done"
    FAILED = "failed"


_PHASE_ORDER: tuple[EnumCloseOutPhase, ...] = (
    EnumCloseOutPhase.MERGE_SWEEP,
    EnumCloseOutPhase.DEPLOY_PLUGIN,
    EnumCloseOutPhase.START_ENV,
    EnumCloseOutPhase.INTEGRATION,
    EnumCloseOutPhase.RELEASE_CHECK,
    EnumCloseOutPhase.REDEPLOY_CHECK,
    EnumCloseOutPhase.DASHBOARD_SWEEP,
)

TERMINAL_PHASES: frozenset[EnumCloseOutPhase] = frozenset(
    {EnumCloseOutPhase.DONE, EnumCloseOutPhase.FAILED}
)


def next_phase(current: EnumCloseOutPhase) -> EnumCloseOutPhase:
    """Return the next phase in the close-out progression."""
    if current == EnumCloseOutPhase.IDLE:
        return EnumCloseOutPhase.MERGE_SWEEP
    if current == EnumCloseOutPhase.DASHBOARD_SWEEP:
        return EnumCloseOutPhase.DONE
    if current in TERMINAL_PHASES:
        msg = f"No next phase from terminal state: {current}"
        raise ValueError(msg)

    idx = _PHASE_ORDER.index(current)
    return _PHASE_ORDER[idx + 1]


class ModelCloseOutState(BaseModel):
    """Immutable FSM state for the close-out pipeline."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    correlation_id: UUID = Field(..., description="Close-out run correlation ID.")
    current_phase: EnumCloseOutPhase = Field(
        default=EnumCloseOutPhase.IDLE, description="Current FSM phase."
    )
    consecutive_failures: int = Field(default=0, ge=0)
    max_consecutive_failures: int = Field(default=3, ge=1)
    dry_run: bool = Field(default=False)
    prs_merged: int = Field(default=0, ge=0)
    prs_polished: int = Field(default=0, ge=0)
    error_message: str | None = Field(default=None)


__all__: list[str] = [
    "TERMINAL_PHASES",
    "EnumCloseOutPhase",
    "ModelCloseOutState",
    "next_phase",
]

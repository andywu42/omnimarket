"""ModelHostileReviewerState and EnumHostileReviewerPhase for the hostile reviewer FSM."""

from __future__ import annotations

from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class EnumHostileReviewerPhase(StrEnum):
    """FSM phases for the hostile reviewer.

    Phase Transitions:
        INIT -> DISPATCH_REVIEWS -> AGGREGATE -> CONVERGENCE_CHECK -> REPORT -> DONE
        Any -> FAILED: Circuit breaker tripped or unrecoverable error
    """

    INIT = "init"
    DISPATCH_REVIEWS = "dispatch_reviews"
    AGGREGATE = "aggregate"
    CONVERGENCE_CHECK = "convergence_check"
    REPORT = "report"
    DONE = "done"
    FAILED = "failed"


_PHASE_ORDER: tuple[EnumHostileReviewerPhase, ...] = (
    EnumHostileReviewerPhase.DISPATCH_REVIEWS,
    EnumHostileReviewerPhase.AGGREGATE,
    EnumHostileReviewerPhase.CONVERGENCE_CHECK,
    EnumHostileReviewerPhase.REPORT,
)

TERMINAL_PHASES: frozenset[EnumHostileReviewerPhase] = frozenset(
    {EnumHostileReviewerPhase.DONE, EnumHostileReviewerPhase.FAILED}
)


def next_phase(current: EnumHostileReviewerPhase) -> EnumHostileReviewerPhase:
    """Return the next phase in the hostile reviewer progression."""
    if current == EnumHostileReviewerPhase.INIT:
        return EnumHostileReviewerPhase.DISPATCH_REVIEWS
    if current == EnumHostileReviewerPhase.REPORT:
        return EnumHostileReviewerPhase.DONE
    if current in TERMINAL_PHASES:
        msg = f"No next phase from terminal state: {current}"
        raise ValueError(msg)

    idx = _PHASE_ORDER.index(current)
    return _PHASE_ORDER[idx + 1]


class ModelHostileReviewerState(BaseModel):
    """Immutable FSM state for the hostile reviewer."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    correlation_id: UUID = Field(..., description="Review run correlation ID.")
    current_phase: EnumHostileReviewerPhase = Field(
        default=EnumHostileReviewerPhase.INIT, description="Current FSM phase."
    )
    consecutive_failures: int = Field(default=0, ge=0)
    max_consecutive_failures: int = Field(default=3, ge=1)
    dry_run: bool = Field(default=False)
    pass_count: int = Field(default=0, ge=0, description="Review passes completed.")
    consecutive_clean: int = Field(
        default=0, ge=0, description="Consecutive clean passes."
    )
    total_findings: int = Field(default=0, ge=0)
    error_message: str | None = Field(default=None)


__all__: list[str] = [
    "TERMINAL_PHASES",
    "EnumHostileReviewerPhase",
    "ModelHostileReviewerState",
    "next_phase",
]

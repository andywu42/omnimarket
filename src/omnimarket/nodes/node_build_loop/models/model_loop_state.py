"""ModelLoopState — mutable FSM state for the build loop."""

from __future__ import annotations

from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class EnumBuildLoopPhase(StrEnum):
    """FSM phases for the autonomous build loop.

    Phase Transitions:
        IDLE -> CLOSING_OUT: Build loop started
        IDLE -> VERIFYING: Build loop started with skip_closeout
        CLOSING_OUT -> VERIFYING: Close-out complete
        VERIFYING -> FILLING: Verification passed
        FILLING -> CLASSIFYING: Backlog filled
        CLASSIFYING -> BUILDING: Tickets classified
        BUILDING -> COMPLETE: All builds dispatched
        Any -> FAILED: Circuit breaker tripped or unrecoverable error
    """

    IDLE = "idle"
    CLOSING_OUT = "closing_out"
    VERIFYING = "verifying"
    FILLING = "filling"
    CLASSIFYING = "classifying"
    BUILDING = "building"
    COMPLETE = "complete"
    FAILED = "failed"


# Ordered phase progression (excluding IDLE, COMPLETE, FAILED which are control states)
_PHASE_ORDER: tuple[EnumBuildLoopPhase, ...] = (
    EnumBuildLoopPhase.CLOSING_OUT,
    EnumBuildLoopPhase.VERIFYING,
    EnumBuildLoopPhase.FILLING,
    EnumBuildLoopPhase.CLASSIFYING,
    EnumBuildLoopPhase.BUILDING,
)

TERMINAL_PHASES: frozenset[EnumBuildLoopPhase] = frozenset(
    {EnumBuildLoopPhase.COMPLETE, EnumBuildLoopPhase.FAILED}
)


def next_phase(
    current: EnumBuildLoopPhase, skip_closeout: bool = False
) -> EnumBuildLoopPhase:
    """Return the next phase in the build loop progression.

    Returns COMPLETE after BUILDING. Raises ValueError for terminal phases.
    """
    if current == EnumBuildLoopPhase.IDLE:
        return (
            EnumBuildLoopPhase.VERIFYING
            if skip_closeout
            else EnumBuildLoopPhase.CLOSING_OUT
        )
    if current == EnumBuildLoopPhase.BUILDING:
        return EnumBuildLoopPhase.COMPLETE
    if current in TERMINAL_PHASES:
        msg = f"No next phase from terminal state: {current}"
        raise ValueError(msg)

    idx = _PHASE_ORDER.index(current)
    # Skip CLOSING_OUT if skip_closeout and we're transitioning from it
    next_idx = idx + 1
    if skip_closeout and _PHASE_ORDER[next_idx] == EnumBuildLoopPhase.CLOSING_OUT:
        next_idx += 1
    return _PHASE_ORDER[next_idx]


class ModelLoopState(BaseModel):
    """Mutable FSM state for the build loop.

    Tracks the current phase, cycle count, consecutive failure count,
    and per-phase metrics. Immutable (frozen) — state transitions produce
    new instances.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    correlation_id: UUID = Field(..., description="Root correlation ID.")
    current_phase: EnumBuildLoopPhase = Field(
        default=EnumBuildLoopPhase.IDLE, description="Current FSM phase."
    )
    cycle_count: int = Field(default=0, ge=0, description="Completed cycles.")
    consecutive_failures: int = Field(
        default=0, ge=0, description="Consecutive phase failures."
    )
    max_consecutive_failures: int = Field(
        default=3, ge=1, description="Circuit breaker threshold."
    )
    skip_closeout: bool = Field(default=False, description="Skip CLOSING_OUT phase.")
    dry_run: bool = Field(default=False, description="No side effects.")
    tickets_filled: int = Field(default=0, ge=0)
    tickets_classified: int = Field(default=0, ge=0)
    tickets_dispatched: int = Field(default=0, ge=0)
    error_message: str | None = Field(default=None)


__all__: list[str] = [
    "TERMINAL_PHASES",
    "EnumBuildLoopPhase",
    "ModelLoopState",
    "next_phase",
]

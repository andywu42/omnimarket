# SPDX-FileCopyrightText: 2025 OmniNode.ai Inc.
# SPDX-License-Identifier: MIT
"""NodePlatformReadiness — Unified platform readiness gate.

Aggregates verification dimensions into a tri-state report:
- PASS: Dimension healthy, data fresh
- WARN: Dimension degraded or data stale (>24h)
- FAIL: Dimension broken, data missing (>72h), or mock data

ONEX node type: COMPUTE
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class EnumReadinessStatus(StrEnum):
    """Tri-state readiness status."""

    PASS = "PASS"
    WARN = "WARN"
    FAIL = "FAIL"


class ModelDimensionResult(BaseModel):
    """Result for a single readiness dimension."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    status: EnumReadinessStatus
    critical: bool
    freshness: str  # "current", "Xh ago", "stale", "missing"
    details: str


class ModelDimensionInput(BaseModel):
    """Input data for a single readiness dimension."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    critical: bool = False
    healthy: bool | None = None  # None = missing/not measured
    last_checked: datetime | None = None
    details: str = ""
    is_mock: bool = False


class ModelPlatformReadinessRequest(BaseModel):
    """Input for the platform readiness handler."""

    model_config = ConfigDict(extra="forbid")

    dimensions: list[ModelDimensionInput]
    now: datetime | None = None  # Allow injection for testing


class ModelPlatformReadinessResult(BaseModel):
    """Output of the platform readiness handler."""

    model_config = ConfigDict(extra="forbid")

    overall: EnumReadinessStatus = EnumReadinessStatus.PASS
    dimensions: list[ModelDimensionResult] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    degraded: list[str] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


_STALE_THRESHOLD = timedelta(hours=24)
_MISSING_THRESHOLD = timedelta(hours=72)

# Legacy aliases for backward compatibility with existing tests
ReadinessStatus = EnumReadinessStatus
DimensionResult = ModelDimensionResult
DimensionInput = ModelDimensionInput
PlatformReadinessRequest = ModelPlatformReadinessRequest
PlatformReadinessResult = ModelPlatformReadinessResult


class NodePlatformReadiness:
    """Aggregate verification dimensions into a readiness report."""

    def handle(
        self, request: ModelPlatformReadinessRequest
    ) -> ModelPlatformReadinessResult:
        """Evaluate all dimensions and produce readiness report."""
        now = request.now or datetime.now(UTC)
        results: list[ModelDimensionResult] = []
        blockers: list[str] = []
        degraded: list[str] = []

        for dim in request.dimensions:
            result = self._evaluate_dimension(dim, now)
            results.append(result)

            if result.status == EnumReadinessStatus.FAIL:
                blockers.append(f"{result.name}: {result.details}")
            elif result.status == EnumReadinessStatus.WARN:
                degraded.append(f"{result.name}: {result.details}")

        # Overall status
        if blockers:
            overall = EnumReadinessStatus.FAIL
        elif degraded:
            overall = EnumReadinessStatus.WARN
        else:
            overall = EnumReadinessStatus.PASS

        return ModelPlatformReadinessResult(
            overall=overall,
            dimensions=results,
            blockers=blockers,
            degraded=degraded,
            timestamp=now,
        )

    def _evaluate_dimension(
        self, dim: ModelDimensionInput, now: datetime
    ) -> ModelDimensionResult:
        """Evaluate a single dimension with freshness rules."""
        # Mock data is always FAIL
        if dim.is_mock:
            return ModelDimensionResult(
                name=dim.name,
                status=EnumReadinessStatus.FAIL,
                critical=dim.critical,
                freshness="mock",
                details=f"Mock data detected: {dim.details}",
            )

        # Missing data
        if dim.healthy is None or dim.last_checked is None:
            return ModelDimensionResult(
                name=dim.name,
                status=EnumReadinessStatus.FAIL,
                critical=dim.critical,
                freshness="missing",
                details=dim.details or "No data available",
            )

        # Freshness check
        age = now - dim.last_checked
        if age > _MISSING_THRESHOLD:
            freshness = f">{int(age.total_seconds() / 3600)}h (missing)"
            return ModelDimensionResult(
                name=dim.name,
                status=EnumReadinessStatus.FAIL,
                critical=dim.critical,
                freshness=freshness,
                details=f"Data too old to trust ({freshness})",
            )

        if age > _STALE_THRESHOLD:
            freshness = f"{int(age.total_seconds() / 3600)}h ago (stale)"
            return ModelDimensionResult(
                name=dim.name,
                status=EnumReadinessStatus.WARN,
                critical=dim.critical,
                freshness=freshness,
                details=dim.details or f"Stale data ({freshness})",
            )

        # Fresh data — use actual status
        hours = int(age.total_seconds() / 3600)
        freshness = "current" if hours == 0 else f"{hours}h ago"
        status = EnumReadinessStatus.PASS if dim.healthy else EnumReadinessStatus.FAIL

        return ModelDimensionResult(
            name=dim.name,
            status=status,
            critical=dim.critical,
            freshness=freshness,
            details=dim.details or ("Healthy" if dim.healthy else "Unhealthy"),
        )

"""NodePlatformReadiness — Unified platform readiness gate.

Aggregates verification dimensions into a tri-state report:
- PASS: Dimension healthy, data fresh
- WARN: Dimension degraded or data stale (>24h)
- FAIL: Dimension broken, data missing (>72h), or mock data

ONEX node type: COMPUTE
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import Enum


class ReadinessStatus(Enum):
    """Tri-state readiness status."""

    PASS = "PASS"
    WARN = "WARN"
    FAIL = "FAIL"


@dataclass
class DimensionResult:
    """Result for a single readiness dimension."""

    name: str
    status: ReadinessStatus
    critical: bool
    freshness: str  # "current", "Xh ago", "stale", "missing"
    details: str


@dataclass
class DimensionInput:
    """Input data for a single readiness dimension."""

    name: str
    critical: bool = False
    healthy: bool | None = None  # None = missing/not measured
    last_checked: datetime | None = None
    details: str = ""
    is_mock: bool = False


@dataclass
class PlatformReadinessRequest:
    """Input for the platform readiness handler."""

    dimensions: list[DimensionInput]
    now: datetime | None = None  # Allow injection for testing


@dataclass
class PlatformReadinessResult:
    """Output of the platform readiness handler."""

    overall: ReadinessStatus = ReadinessStatus.PASS
    dimensions: list[DimensionResult] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)
    degraded: list[str] = field(default_factory=list)
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))


_STALE_THRESHOLD = timedelta(hours=24)
_MISSING_THRESHOLD = timedelta(hours=72)


class NodePlatformReadiness:
    """Aggregate verification dimensions into a readiness report."""

    def handle(self, request: PlatformReadinessRequest) -> PlatformReadinessResult:
        """Evaluate all dimensions and produce readiness report."""
        now = request.now or datetime.now(UTC)
        results: list[DimensionResult] = []
        blockers: list[str] = []
        degraded: list[str] = []

        for dim in request.dimensions:
            result = self._evaluate_dimension(dim, now)
            results.append(result)

            if result.status == ReadinessStatus.FAIL:
                blockers.append(f"{result.name}: {result.details}")
            elif result.status == ReadinessStatus.WARN:
                degraded.append(f"{result.name}: {result.details}")

        # Overall status
        if blockers:
            overall = ReadinessStatus.FAIL
        elif degraded:
            overall = ReadinessStatus.WARN
        else:
            overall = ReadinessStatus.PASS

        return PlatformReadinessResult(
            overall=overall,
            dimensions=results,
            blockers=blockers,
            degraded=degraded,
            timestamp=now,
        )

    def _evaluate_dimension(
        self, dim: DimensionInput, now: datetime
    ) -> DimensionResult:
        """Evaluate a single dimension with freshness rules."""
        # Mock data is always FAIL
        if dim.is_mock:
            return DimensionResult(
                name=dim.name,
                status=ReadinessStatus.FAIL,
                critical=dim.critical,
                freshness="mock",
                details=f"Mock data detected: {dim.details}",
            )

        # Missing data
        if dim.healthy is None or dim.last_checked is None:
            return DimensionResult(
                name=dim.name,
                status=ReadinessStatus.FAIL,
                critical=dim.critical,
                freshness="missing",
                details=dim.details or "No data available",
            )

        # Freshness check
        age = now - dim.last_checked
        if age > _MISSING_THRESHOLD:
            freshness = f">{int(age.total_seconds() / 3600)}h (missing)"
            return DimensionResult(
                name=dim.name,
                status=ReadinessStatus.FAIL,
                critical=dim.critical,
                freshness=freshness,
                details=f"Data too old to trust ({freshness})",
            )

        if age > _STALE_THRESHOLD:
            freshness = f"{int(age.total_seconds() / 3600)}h ago (stale)"
            return DimensionResult(
                name=dim.name,
                status=ReadinessStatus.WARN,
                critical=dim.critical,
                freshness=freshness,
                details=dim.details or f"Stale data ({freshness})",
            )

        # Fresh data — use actual status
        hours = int(age.total_seconds() / 3600)
        freshness = "current" if hours == 0 else f"{hours}h ago"
        status = ReadinessStatus.PASS if dim.healthy else ReadinessStatus.FAIL

        return DimensionResult(
            name=dim.name,
            status=status,
            critical=dim.critical,
            freshness=freshness,
            details=dim.details or ("Healthy" if dim.healthy else "Unhealthy"),
        )

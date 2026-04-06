"""NodeDashboardSweep — Dashboard page classification and triage.

Classifies dashboard pages as HEALTHY, EMPTY, MOCK, BROKEN, or FLAG_GATED,
then groups them into problem domains and assigns fix tiers (CODE_BUG,
DATA_PIPELINE, SCHEMA_MISMATCH, FEATURE_GAP, FLAG_GATE).

ONEX node type: COMPUTE — pure, deterministic, no LLM calls.
"""

from __future__ import annotations

import re
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class EnumPageStatus(StrEnum):
    """Dashboard page classification status."""

    HEALTHY = "HEALTHY"
    EMPTY = "EMPTY"
    MOCK = "MOCK"
    BROKEN = "BROKEN"
    FLAG_GATED = "FLAG_GATED"


class EnumFixTier(StrEnum):
    """Fix tier for a problem domain."""

    CODE_BUG = "CODE_BUG"
    DATA_PIPELINE = "DATA_PIPELINE"
    SCHEMA_MISMATCH = "SCHEMA_MISMATCH"
    FEATURE_GAP = "FEATURE_GAP"
    FLAG_GATE = "FLAG_GATE"


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class ModelPageInput(BaseModel):
    """Input for a single dashboard page."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    route: str
    has_data: bool = False
    has_live_timestamps: bool = False
    has_js_errors: bool = False
    has_network_errors: bool = False
    has_mock_patterns: bool = False
    has_feature_flag: bool = False
    visible_text: str = ""


class ModelPageStatus(BaseModel):
    """Classification result for a single page."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    route: str
    status: EnumPageStatus
    reason: str


class ModelProblemDomain(BaseModel):
    """A grouped problem domain with fix tier."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    domain_id: str
    pages: list[str]
    fix_tier: EnumFixTier
    hypothesis: str


class DashboardSweepRequest(BaseModel):
    """Input for the dashboard sweep handler."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    pages: list[ModelPageInput] = Field(default_factory=list)
    max_iterations: int = 3
    dry_run: bool = False


class DashboardSweepResult(BaseModel):
    """Output of the dashboard sweep handler."""

    model_config = ConfigDict(extra="forbid")

    page_statuses: list[ModelPageStatus] = Field(default_factory=list)
    domains: list[ModelProblemDomain] = Field(default_factory=list)
    pages_total: int = 0
    status: str = "clean"  # clean | issues_found | error
    dry_run: bool = False

    @property
    def by_status(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for ps in self.page_statuses:
            counts[ps.status] = counts.get(ps.status, 0) + 1
        return counts

    @property
    def by_fix_tier(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for d in self.domains:
            counts[d.fix_tier] = counts.get(d.fix_tier, 0) + 1
        return counts


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_MOCK_PATTERNS = [
    re.compile(r"Sample\s+Agent", re.IGNORECASE),
    re.compile(r"lorem\s+ipsum", re.IGNORECASE),
    re.compile(r"count:\s*42\b"),
    re.compile(r"placeholder", re.IGNORECASE),
    re.compile(r"example\.com"),
]


# ---------------------------------------------------------------------------
# Handler
# ---------------------------------------------------------------------------


class NodeDashboardSweep:
    """Classify dashboard pages and triage into problem domains.

    Pure compute handler — operates on page metadata, no browser interaction.
    """

    def handle(self, request: DashboardSweepRequest) -> DashboardSweepResult:
        """Execute the dashboard sweep across page inputs."""
        page_statuses: list[ModelPageStatus] = []
        broken_pages: list[ModelPageStatus] = []

        for page in request.pages:
            status = self._classify_page(page)
            page_statuses.append(status)
            if status.status in (EnumPageStatus.BROKEN, EnumPageStatus.EMPTY):
                broken_pages.append(status)

        domains = self._triage_domains(broken_pages, request.pages)

        overall = "clean" if not broken_pages else "issues_found"

        return DashboardSweepResult(
            page_statuses=page_statuses,
            domains=domains,
            pages_total=len(request.pages),
            status=overall,
            dry_run=request.dry_run,
        )

    def _classify_page(self, page: ModelPageInput) -> ModelPageStatus:
        """Classify a single page using the decision tree."""
        if page.has_js_errors or page.has_network_errors:
            return ModelPageStatus(
                route=page.route,
                status=EnumPageStatus.BROKEN,
                reason="JS error or network failure detected",
            )

        if page.has_mock_patterns or self._detect_mock_text(page.visible_text):
            return ModelPageStatus(
                route=page.route,
                status=EnumPageStatus.MOCK,
                reason="Mock/placeholder data detected",
            )

        if page.has_data and page.has_live_timestamps:
            return ModelPageStatus(
                route=page.route,
                status=EnumPageStatus.HEALTHY,
                reason="Real data with live timestamps",
            )

        if page.has_feature_flag:
            return ModelPageStatus(
                route=page.route,
                status=EnumPageStatus.FLAG_GATED,
                reason="Feature flag not set",
            )

        return ModelPageStatus(
            route=page.route,
            status=EnumPageStatus.EMPTY,
            reason="No data visible",
        )

    def _detect_mock_text(self, text: str) -> bool:
        """Check if visible text contains known mock patterns."""
        return any(p.search(text) for p in _MOCK_PATTERNS)

    def _triage_domains(
        self,
        broken_pages: list[ModelPageStatus],
        all_pages: list[ModelPageInput],
    ) -> list[ModelProblemDomain]:
        """Group broken/empty pages into problem domains with fix tiers."""
        domains: list[ModelProblemDomain] = []
        page_input_map = {p.route: p for p in all_pages}

        for ps in broken_pages:
            page_input = page_input_map.get(ps.route)
            if not page_input:
                continue

            if ps.status == EnumPageStatus.BROKEN:
                if page_input.has_js_errors:
                    fix_tier = EnumFixTier.CODE_BUG
                    hypothesis = "JS error in page rendering"
                else:
                    fix_tier = EnumFixTier.CODE_BUG
                    hypothesis = "Network or API failure"
            else:
                fix_tier = EnumFixTier.DATA_PIPELINE
                hypothesis = "Data not reaching the page — pipeline gap"

            domain_id = ps.route.strip("/").replace("/", "-") or "root"
            domains.append(
                ModelProblemDomain(
                    domain_id=domain_id,
                    pages=[ps.route],
                    fix_tier=fix_tier,
                    hypothesis=hypothesis,
                )
            )

        return domains

# SPDX-FileCopyrightText: 2025 OmniNode.ai Inc.
# SPDX-License-Identifier: MIT
"""NodeMergeSweep — Org-wide PR classification and merge orchestration.

Classifies open PRs into tracks:
- Track A-update: Stale branches needing update before merge
- Track A: Merge-ready PRs for auto-merge
- Track A-resolve: PRs blocked only by unresolved review threads
- Track B: PRs with fixable blocking issues for polish

ONEX node type: ORCHESTRATOR
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class EnumPRTrack(StrEnum):
    """Classification track for a PR."""

    A_UPDATE = "A-update"
    A_MERGE = "A"
    A_RESOLVE = "A-resolve"
    B_POLISH = "B"
    SKIP = "skip"


class EnumFailureCategory(StrEnum):
    """Standardized failure category strings for cross-run failure history."""

    CI_TEST = "ci_test"
    CI_LINT = "ci_lint"
    CI_GATE = "ci_gate"
    PR_TITLE = "pr_title"
    CONFLICT = "conflict"
    CHANGES_REQUESTED = "changes_requested"
    THREADS_BLOCKED = "threads_blocked"
    BRANCH_STALE = "branch_stale"
    SCAN_FAILED = "scan_failed"
    POLISH_FAILED = "polish_failed"
    NEEDS_HUMAN = "needs_human"


class ModelPRInfo(BaseModel):
    """Minimal PR representation for classification."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    number: int
    title: str
    repo: str
    mergeable: str  # MERGEABLE | CONFLICTING | UNKNOWN
    merge_state_status: str  # BEHIND | BLOCKED | CLEAN | DIRTY | DRAFT | UNKNOWN
    is_draft: bool = False
    review_decision: str | None = None  # APPROVED | CHANGES_REQUESTED | None
    required_checks_pass: bool = True
    labels: list[str] = Field(default_factory=list)


class ModelClassifiedPR(BaseModel):
    """A PR with its classification track."""

    model_config = ConfigDict(extra="forbid")

    pr: ModelPRInfo
    track: EnumPRTrack
    reason: str
    failure_categories: list[str] = Field(default_factory=list)


class ModelFailureHistoryEntry(BaseModel):
    """Cross-run failure tracking for a single PR."""

    model_config = ConfigDict(extra="forbid")

    first_seen: str
    last_seen: str
    consecutive_failures: int = 0
    total_failures: int = 0
    total_polishes: int = 0
    last_failure_categories: list[str] = Field(default_factory=list)
    last_result: str | None = None
    last_run_id: str | None = None
    runs_seen: list[str] = Field(default_factory=list)


class ModelFailureHistorySummary(BaseModel):
    """Aggregate failure history stats for ModelSkillResult."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    total_tracked: int = 0
    stuck_prs: int = 0
    chronic_prs: int = 0
    recidivist_prs: int = 0
    cleaned_merged: int = 0


class ModelMergeSweepRequest(BaseModel):
    """Input for the merge sweep handler."""

    model_config = ConfigDict(extra="forbid")

    prs: list[ModelPRInfo]
    require_approval: bool = True
    merge_method: str = "squash"
    max_total_merges: int = 0
    skip_polish: bool = False
    failure_history: dict[str, ModelFailureHistoryEntry] = Field(default_factory=dict)
    run_id: str = ""


class ModelMergeSweepResult(BaseModel):
    """Output of the merge sweep handler."""

    model_config = ConfigDict(extra="forbid")

    classified: list[ModelClassifiedPR] = Field(default_factory=list)
    status: str = "nothing_to_merge"
    failure_history_summary: ModelFailureHistorySummary = Field(
        default_factory=ModelFailureHistorySummary
    )

    @property
    def track_a_update(self) -> list[ModelClassifiedPR]:
        return [c for c in self.classified if c.track == EnumPRTrack.A_UPDATE]

    @property
    def track_a_merge(self) -> list[ModelClassifiedPR]:
        return [c for c in self.classified if c.track == EnumPRTrack.A_MERGE]

    @property
    def track_a_resolve(self) -> list[ModelClassifiedPR]:
        return [c for c in self.classified if c.track == EnumPRTrack.A_RESOLVE]

    @property
    def track_b_polish(self) -> list[ModelClassifiedPR]:
        return [c for c in self.classified if c.track == EnumPRTrack.B_POLISH]

    @property
    def skipped(self) -> list[ModelClassifiedPR]:
        return [c for c in self.classified if c.track == EnumPRTrack.SKIP]


# Legacy aliases for backward compatibility with existing tests
PRTrack = EnumPRTrack
FailureCategory = EnumFailureCategory
PRInfo = ModelPRInfo
ClassifiedPR = ModelClassifiedPR
FailureHistoryEntry = ModelFailureHistoryEntry
FailureHistorySummary = ModelFailureHistorySummary
MergeSweepRequest = ModelMergeSweepRequest
MergeSweepResult = ModelMergeSweepResult


class NodeMergeSweep:
    """Classify PRs into merge/polish/skip tracks."""

    # Escalation thresholds
    STUCK_THRESHOLD = 3
    CHRONIC_THRESHOLD = 5
    RECIDIVIST_POLISH_THRESHOLD = 3

    def handle(self, request: ModelMergeSweepRequest) -> ModelMergeSweepResult:
        """Classify all PRs and return the result."""
        classified: list[ModelClassifiedPR] = []

        for pr in request.prs:
            track, reason, categories = self._classify_pr(pr, request.require_approval)
            classified.append(
                ModelClassifiedPR(
                    pr=pr, track=track, reason=reason, failure_categories=categories
                )
            )

        # Apply max_total_merges cap to Track A
        if request.max_total_merges > 0:
            merge_count = 0
            for c in classified:
                if c.track == EnumPRTrack.A_MERGE:
                    merge_count += 1
                    if merge_count > request.max_total_merges:
                        c.track = EnumPRTrack.SKIP
                        c.reason = "Exceeds max_total_merges cap"

        # Remove Track B if skip_polish
        if request.skip_polish:
            for c in classified:
                if c.track == EnumPRTrack.B_POLISH:
                    c.track = EnumPRTrack.SKIP
                    c.reason = "Polish skipped (--skip-polish)"

        # Apply failure history escalation to Track B
        for c in classified:
            if c.track == EnumPRTrack.B_POLISH:
                skip, skip_reason = self._should_skip_polish(
                    request.failure_history, f"{c.pr.repo}#{c.pr.number}"
                )
                if skip:
                    c.track = EnumPRTrack.SKIP
                    c.reason = skip_reason or "Skipped by failure history"

        has_actionable = any(
            c.track
            in (
                EnumPRTrack.A_UPDATE,
                EnumPRTrack.A_MERGE,
                EnumPRTrack.A_RESOLVE,
                EnumPRTrack.B_POLISH,
            )
            for c in classified
        )
        status = "queued" if has_actionable else "nothing_to_merge"

        # Compute failure history summary
        summary = self._compute_failure_summary(request.failure_history)

        return ModelMergeSweepResult(
            classified=classified, status=status, failure_history_summary=summary
        )

    def _classify_pr(
        self, pr: ModelPRInfo, require_approval: bool
    ) -> tuple[EnumPRTrack, str, list[str]]:
        """Classify a single PR. First match wins. Returns (track, reason, categories)."""
        if pr.is_draft:
            return EnumPRTrack.SKIP, "Draft PR", []

        # Track A-update: stale branches or unknown mergeable state
        if self._needs_branch_update(pr):
            return (
                EnumPRTrack.A_UPDATE,
                f"Branch stale ({pr.merge_state_status})",
                [EnumFailureCategory.BRANCH_STALE.value],
            )

        # Track A: merge-ready
        if self._is_merge_ready(pr, require_approval):
            return EnumPRTrack.A_MERGE, "Merge-ready", []

        # Track A-resolve: BLOCKED by unresolved threads only
        if self._needs_thread_resolution(pr):
            return (
                EnumPRTrack.A_RESOLVE,
                "Blocked by unresolved review threads",
                [EnumFailureCategory.THREADS_BLOCKED.value],
            )

        # Track B: fixable blocking issues
        if self._needs_polish(pr, require_approval):
            categories: list[str] = []
            reason_parts: list[str] = []
            if pr.mergeable == "CONFLICTING":
                reason_parts.append("conflicts")
                categories.append(EnumFailureCategory.CONFLICT.value)
            if not pr.required_checks_pass:
                reason_parts.append("CI failing")
                categories.append(EnumFailureCategory.CI_TEST.value)
            if require_approval and pr.review_decision == "CHANGES_REQUESTED":
                reason_parts.append("changes requested")
                categories.append(EnumFailureCategory.CHANGES_REQUESTED.value)
            return (
                EnumPRTrack.B_POLISH,
                "Needs polish: " + ", ".join(reason_parts),
                categories,
            )

        return EnumPRTrack.SKIP, "No actionable state", []

    def _needs_branch_update(self, pr: ModelPRInfo) -> bool:
        if pr.mergeable == "MERGEABLE":
            return pr.merge_state_status.upper() in ("BEHIND", "UNKNOWN")
        if pr.mergeable == "UNKNOWN":
            return True
        return False

    def _is_merge_ready(self, pr: ModelPRInfo, require_approval: bool) -> bool:
        if pr.mergeable != "MERGEABLE":
            return False
        if pr.merge_state_status.upper() == "BLOCKED":
            return False  # BLOCKED PRs may need thread resolution
        if not pr.required_checks_pass:
            return False
        if require_approval:
            return pr.review_decision in ("APPROVED", None)
        return True

    def _needs_thread_resolution(self, pr: ModelPRInfo) -> bool:
        """MERGEABLE + BLOCKED + GREEN = blocked by required_conversation_resolution."""
        if pr.mergeable != "MERGEABLE":
            return False
        if pr.merge_state_status.upper() != "BLOCKED":
            return False
        if not pr.required_checks_pass:
            return False
        return True

    def _needs_polish(self, pr: ModelPRInfo, require_approval: bool) -> bool:
        if pr.mergeable == "UNKNOWN":
            return False
        if self._is_merge_ready(pr, require_approval):
            return False
        if pr.mergeable == "CONFLICTING":
            return True
        if not pr.required_checks_pass:
            return True
        if require_approval and pr.review_decision == "CHANGES_REQUESTED":
            return True
        return False

    def _should_skip_polish(
        self, history: dict[str, ModelFailureHistoryEntry], pr_key: str
    ) -> tuple[bool, str | None]:
        """Check if a PR should skip polish based on failure history."""
        entry = history.get(pr_key)
        if not entry:
            return False, None
        if entry.consecutive_failures >= self.CHRONIC_THRESHOLD:
            return (
                True,
                f"CHRONIC: {entry.consecutive_failures} consecutive failures — skipping polish",
            )
        if (
            entry.total_polishes >= self.RECIDIVIST_POLISH_THRESHOLD
            and entry.consecutive_failures > 0
        ):
            return (
                True,
                f"RECIDIVIST: polished {entry.total_polishes}x, still failing — skipping polish",
            )
        return False, None

    def _compute_failure_summary(
        self, history: dict[str, ModelFailureHistoryEntry]
    ) -> ModelFailureHistorySummary:
        """Compute aggregate failure history stats."""
        stuck = 0
        chronic = 0
        recidivist = 0
        for entry in history.values():
            if entry.consecutive_failures >= self.CHRONIC_THRESHOLD:
                chronic += 1
            elif entry.consecutive_failures >= self.STUCK_THRESHOLD:
                stuck += 1
            if (
                entry.total_polishes >= self.RECIDIVIST_POLISH_THRESHOLD
                and entry.consecutive_failures > 0
            ):
                recidivist += 1
        return ModelFailureHistorySummary(
            total_tracked=len(history),
            stuck_prs=stuck,
            chronic_prs=chronic,
            recidivist_prs=recidivist,
        )

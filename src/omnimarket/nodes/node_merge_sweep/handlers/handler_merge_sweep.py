"""NodeMergeSweep — Org-wide PR classification and merge orchestration.

Classifies open PRs into tracks:
- Track A-update: Stale branches needing update before merge
- Track A: Merge-ready PRs for auto-merge
- Track B: PRs with fixable blocking issues for polish

ONEX node type: ORCHESTRATOR
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class PRTrack(Enum):
    """Classification track for a PR."""

    A_UPDATE = "A-update"
    A_MERGE = "A"
    B_POLISH = "B"
    SKIP = "skip"


@dataclass
class PRInfo:
    """Minimal PR representation for classification."""

    number: int
    title: str
    repo: str
    mergeable: str  # MERGEABLE | CONFLICTING | UNKNOWN
    merge_state_status: str  # BEHIND | BLOCKED | CLEAN | DIRTY | DRAFT | UNKNOWN
    is_draft: bool = False
    review_decision: str | None = None  # APPROVED | CHANGES_REQUESTED | None
    required_checks_pass: bool = True
    labels: list[str] = field(default_factory=list)


@dataclass
class ClassifiedPR:
    """A PR with its classification track."""

    pr: PRInfo
    track: PRTrack
    reason: str


@dataclass
class MergeSweepRequest:
    """Input for the merge sweep handler."""

    prs: list[PRInfo]
    require_approval: bool = True
    merge_method: str = "squash"
    max_total_merges: int = 0
    skip_polish: bool = False


@dataclass
class MergeSweepResult:
    """Output of the merge sweep handler."""

    classified: list[ClassifiedPR] = field(default_factory=list)
    status: str = "nothing_to_merge"

    @property
    def track_a_update(self) -> list[ClassifiedPR]:
        return [c for c in self.classified if c.track == PRTrack.A_UPDATE]

    @property
    def track_a_merge(self) -> list[ClassifiedPR]:
        return [c for c in self.classified if c.track == PRTrack.A_MERGE]

    @property
    def track_b_polish(self) -> list[ClassifiedPR]:
        return [c for c in self.classified if c.track == PRTrack.B_POLISH]

    @property
    def skipped(self) -> list[ClassifiedPR]:
        return [c for c in self.classified if c.track == PRTrack.SKIP]


class NodeMergeSweep:
    """Classify PRs into merge/polish/skip tracks."""

    def handle(self, request: MergeSweepRequest) -> MergeSweepResult:
        """Classify all PRs and return the result."""
        classified: list[ClassifiedPR] = []

        for pr in request.prs:
            track, reason = self._classify_pr(pr, request.require_approval)
            classified.append(ClassifiedPR(pr=pr, track=track, reason=reason))

        # Apply max_total_merges cap to Track A
        if request.max_total_merges > 0:
            merge_count = 0
            for c in classified:
                if c.track == PRTrack.A_MERGE:
                    merge_count += 1
                    if merge_count > request.max_total_merges:
                        c.track = PRTrack.SKIP
                        c.reason = "Exceeds max_total_merges cap"

        # Remove Track B if skip_polish
        if request.skip_polish:
            for c in classified:
                if c.track == PRTrack.B_POLISH:
                    c.track = PRTrack.SKIP
                    c.reason = "Polish skipped (--skip-polish)"

        has_actionable = any(
            c.track in (PRTrack.A_UPDATE, PRTrack.A_MERGE, PRTrack.B_POLISH)
            for c in classified
        )
        status = "queued" if has_actionable else "nothing_to_merge"

        return MergeSweepResult(classified=classified, status=status)

    def _classify_pr(self, pr: PRInfo, require_approval: bool) -> tuple[PRTrack, str]:
        """Classify a single PR. First match wins."""
        if pr.is_draft:
            return PRTrack.SKIP, "Draft PR"

        # Track A-update: stale branches or unknown mergeable state
        if self._needs_branch_update(pr):
            return PRTrack.A_UPDATE, f"Branch stale ({pr.merge_state_status})"

        # Track A: merge-ready
        if self._is_merge_ready(pr, require_approval):
            return PRTrack.A_MERGE, "Merge-ready"

        # Track B: fixable blocking issues
        if self._needs_polish(pr, require_approval):
            reason_parts = []
            if pr.mergeable == "CONFLICTING":
                reason_parts.append("conflicts")
            if not pr.required_checks_pass:
                reason_parts.append("CI failing")
            if require_approval and pr.review_decision == "CHANGES_REQUESTED":
                reason_parts.append("changes requested")
            return PRTrack.B_POLISH, "Needs polish: " + ", ".join(reason_parts)

        return PRTrack.SKIP, "No actionable state"

    def _needs_branch_update(self, pr: PRInfo) -> bool:
        if pr.mergeable == "MERGEABLE":
            return pr.merge_state_status.upper() in ("BEHIND", "UNKNOWN")
        if pr.mergeable == "UNKNOWN":
            return True
        return False

    def _is_merge_ready(self, pr: PRInfo, require_approval: bool) -> bool:
        if pr.mergeable != "MERGEABLE":
            return False
        if not pr.required_checks_pass:
            return False
        if require_approval:
            return pr.review_decision in ("APPROVED", None)
        return True

    def _needs_polish(self, pr: PRInfo, require_approval: bool) -> bool:
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

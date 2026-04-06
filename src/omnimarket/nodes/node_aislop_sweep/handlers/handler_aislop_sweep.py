"""NodeAislopSweep — Detect AI-generated quality anti-patterns.

Scans repository directories for common AI-slop patterns:
- Prohibited env var patterns (ONEX_EVENT_BUS_TYPE=inmemory, OLLAMA_BASE_URL)
- Hardcoded topic strings (onex.* literals in Python files)
- Backwards-compat shims (# removed, _unused_ vars)
- Empty implementations (bare pass in non-abstract src files)
- TODO/FIXME markers in source code

ONEX node type: COMPUTE — pure, deterministic, no LLM calls.
"""

from __future__ import annotations

import re
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class ModelSweepFinding(BaseModel):
    """A single finding from the aislop sweep."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    repo: str
    path: str
    line: int
    check: str
    message: str
    severity: str  # CRITICAL | ERROR | WARNING | INFO
    confidence: str  # HIGH | MEDIUM | LOW
    autofixable: bool = False

    @property
    def ticketable(self) -> bool:
        """A finding is ticketable when confidence is HIGH and severity >= WARNING."""
        return self.confidence == "HIGH" and self.severity in (
            "CRITICAL",
            "ERROR",
            "WARNING",
        )


class AislopSweepRequest(BaseModel):
    """Input for the aislop sweep handler."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    target_dirs: list[str] = Field(default_factory=list)
    checks: list[str] | None = None
    dry_run: bool = False
    severity_threshold: str = "WARNING"


class AislopSweepResult(BaseModel):
    """Output of the aislop sweep handler."""

    model_config = ConfigDict(extra="forbid")

    findings: list[ModelSweepFinding] = Field(default_factory=list)
    repos_scanned: int = 0
    status: str = "clean"  # clean | findings | partial | error
    dry_run: bool = False

    @property
    def total_findings(self) -> int:
        return len(self.findings)

    @property
    def by_severity(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for f in self.findings:
            counts[f.severity] = counts.get(f.severity, 0) + 1
        return counts

    @property
    def by_check(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for f in self.findings:
            counts[f.check] = counts.get(f.check, 0) + 1
        return counts


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_EXCLUDED_DIRS = {
    ".git",
    ".venv",
    "node_modules",
    "__pycache__",
    "dist",
    "build",
    "docs",
    "examples",
    "fixtures",
    "migrations",
    "vendored",
    "_golden_path_validate",
}

_PROHIBITED_PATTERNS = [
    (
        re.compile(r"ONEX_EVENT_BUS_TYPE\s*=\s*[\"']?inmemory"),
        "ONEX_EVENT_BUS_TYPE=inmemory",
    ),
    (re.compile(r"OLLAMA_BASE_URL"), "OLLAMA_BASE_URL reference"),
]

_HARDCODED_TOPIC_PATTERN = re.compile(r'"onex\.[a-z]+\.[a-z]+\.[a-z]')

_COMPAT_SHIM_PATTERNS = [
    (re.compile(r"#\s*removed"), "# removed comment"),
    (re.compile(r"#\s*backwards?.compat"), "backwards-compat comment"),
    (re.compile(r"_unused_"), "_unused_ variable"),
]

_EMPTY_IMPL_PATTERN = re.compile(r"^\s+pass\s*$")

_TODO_PATTERN = re.compile(r"\b(TODO|FIXME|HACK)\b")


# ---------------------------------------------------------------------------
# Handler
# ---------------------------------------------------------------------------


class NodeAislopSweep:
    """Scan directories for AI-generated quality anti-patterns.

    Pure compute handler — no I/O beyond reading the target directories.
    """

    ALL_CHECKS = [
        "prohibited-patterns",
        "hardcoded-topics",
        "compat-shims",
        "empty-impls",
        "todo-fixme",
    ]

    def handle(self, request: AislopSweepRequest) -> AislopSweepResult:
        """Execute the aislop sweep across target directories."""
        checks = request.checks or self.ALL_CHECKS
        findings: list[ModelSweepFinding] = []
        repos_scanned = 0

        for target_dir in request.target_dirs:
            target = Path(target_dir)
            if not target.is_dir():
                continue
            repos_scanned += 1
            repo_name = target.name

            src_dir = target / "src"
            if not src_dir.is_dir():
                src_dir = target

            py_files = self._collect_python_files(src_dir)

            for py_file in py_files:
                rel_path = str(py_file.relative_to(target))
                lines = self._read_lines(py_file)

                if "prohibited-patterns" in checks:
                    findings.extend(self._check_prohibited(repo_name, rel_path, lines))
                if "hardcoded-topics" in checks:
                    findings.extend(
                        self._check_hardcoded_topics(repo_name, rel_path, lines)
                    )
                if "compat-shims" in checks:
                    findings.extend(
                        self._check_compat_shims(repo_name, rel_path, lines)
                    )
                if "empty-impls" in checks:
                    findings.extend(self._check_empty_impls(repo_name, rel_path, lines))
                if "todo-fixme" in checks:
                    findings.extend(self._check_todos(repo_name, rel_path, lines))

        status = "clean" if not findings else "findings"
        return AislopSweepResult(
            findings=findings,
            repos_scanned=repos_scanned,
            status=status,
            dry_run=request.dry_run,
        )

    def _collect_python_files(self, root: Path) -> list[Path]:
        """Collect .py files, excluding standard directories."""
        results = []
        for py_file in root.rglob("*.py"):
            if any(part in _EXCLUDED_DIRS for part in py_file.parts):
                continue
            results.append(py_file)
        return sorted(results)

    def _read_lines(self, path: Path) -> list[str]:
        """Read file lines, returning empty list on error."""
        try:
            return path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError):
            return []

    def _check_prohibited(
        self, repo: str, path: str, lines: list[str]
    ) -> list[ModelSweepFinding]:
        findings = []
        for i, line in enumerate(lines, 1):
            for pattern, desc in _PROHIBITED_PATTERNS:
                if pattern.search(line):
                    findings.append(
                        ModelSweepFinding(
                            repo=repo,
                            path=path,
                            line=i,
                            check="prohibited-patterns",
                            message=f"Prohibited pattern: {desc}",
                            severity="CRITICAL",
                            confidence="HIGH",
                        )
                    )
        return findings

    def _check_hardcoded_topics(
        self, repo: str, path: str, lines: list[str]
    ) -> list[ModelSweepFinding]:
        if "contract.yaml" in path or "enum" in path.lower():
            return []
        findings = []
        in_src = path.startswith("src/")
        for i, line in enumerate(lines, 1):
            if _HARDCODED_TOPIC_PATTERN.search(line):
                findings.append(
                    ModelSweepFinding(
                        repo=repo,
                        path=path,
                        line=i,
                        check="hardcoded-topics",
                        message=f"Hardcoded topic string: {line.strip()[:80]}",
                        severity="ERROR" if in_src else "WARNING",
                        confidence="HIGH" if in_src else "MEDIUM",
                    )
                )
        return findings

    def _check_compat_shims(
        self, repo: str, path: str, lines: list[str]
    ) -> list[ModelSweepFinding]:
        if "test" in path.lower():
            return []
        findings = []
        for i, line in enumerate(lines, 1):
            for pattern, desc in _COMPAT_SHIM_PATTERNS:
                if pattern.search(line):
                    findings.append(
                        ModelSweepFinding(
                            repo=repo,
                            path=path,
                            line=i,
                            check="compat-shims",
                            message=f"Backwards-compat shim: {desc}",
                            severity="WARNING",
                            confidence="MEDIUM",
                        )
                    )
        return findings

    def _check_empty_impls(
        self, repo: str, path: str, lines: list[str]
    ) -> list[ModelSweepFinding]:
        basename = Path(path).stem
        if any(
            kw in basename.lower()
            for kw in ("abstract", "protocol", "stub", "__init__")
        ):
            return []
        if "test" in path.lower():
            return []
        findings = []
        for i, line in enumerate(lines, 1):
            if _EMPTY_IMPL_PATTERN.match(line):
                findings.append(
                    ModelSweepFinding(
                        repo=repo,
                        path=path,
                        line=i,
                        check="empty-impls",
                        message="Empty implementation (bare pass)",
                        severity="WARNING",
                        confidence="MEDIUM",
                    )
                )
        return findings

    def _check_todos(
        self, repo: str, path: str, lines: list[str]
    ) -> list[ModelSweepFinding]:
        if "test" in path.lower() or "doc" in path.lower():
            return []
        findings = []
        for i, line in enumerate(lines, 1):
            match = _TODO_PATTERN.search(line)
            if match:
                findings.append(
                    ModelSweepFinding(
                        repo=repo,
                        path=path,
                        line=i,
                        check="todo-fixme",
                        message=f"{match.group(0)} marker: {line.strip()[:80]}",
                        severity="WARNING",
                        confidence="MEDIUM",
                    )
                )
        return findings

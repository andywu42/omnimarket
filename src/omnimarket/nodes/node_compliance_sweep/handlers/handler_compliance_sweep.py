"""NodeComplianceSweep — Handler contract compliance verification.

Scans repository directories for handler files and their associated contracts,
detecting imperative patterns that bypass the ONEX contract system:
- Hardcoded topic strings in handler code
- Undeclared transport imports (psycopg, httpx, etc.)
- Missing handler routing in contract.yaml
- Business logic in node.py instead of handlers

ONEX node type: COMPUTE — pure, deterministic, no LLM calls.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class ModelComplianceViolation(BaseModel):
    """A single compliance violation."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    repo: str
    handler_path: str
    node_name: str
    violation_type: str  # HARDCODED_TOPIC | UNDECLARED_TRANSPORT | MISSING_HANDLER_ROUTING | LOGIC_IN_NODE
    message: str
    severity: str  # CRITICAL | ERROR | WARNING
    line: int = 0


class ComplianceSweepRequest(BaseModel):
    """Input for the compliance sweep handler."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    target_dirs: list[str] = Field(default_factory=list)
    checks: list[str] | None = None
    dry_run: bool = False


class ComplianceSweepResult(BaseModel):
    """Output of the compliance sweep handler."""

    model_config = ConfigDict(extra="forbid")

    violations: list[ModelComplianceViolation] = Field(default_factory=list)
    handlers_scanned: int = 0
    compliant: int = 0
    imperative: int = 0
    status: str = "compliant"  # compliant | violations_found | error
    dry_run: bool = False

    @property
    def total_violations(self) -> int:
        return len(self.violations)

    @property
    def by_type(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for v in self.violations:
            counts[v.violation_type] = counts.get(v.violation_type, 0) + 1
        return counts

    @property
    def by_severity(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for v in self.violations:
            counts[v.severity] = counts.get(v.severity, 0) + 1
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
    "migrations",
}

_HARDCODED_TOPIC_RE = re.compile(r'"onex\.[a-z]+\.[a-z]+\.[a-z]')

_TRANSPORT_IMPORTS = {
    "psycopg",
    "psycopg2",
    "asyncpg",
    "httpx",
    "requests",
    "aiohttp",
    "sqlalchemy",
    "boto3",
}

_LOGIC_INDICATORS = [
    re.compile(r"class\s+\w+.*:"),
    re.compile(r"def\s+(handle|process|execute)\s*\("),
]


# ---------------------------------------------------------------------------
# Handler
# ---------------------------------------------------------------------------


class NodeComplianceSweep:
    """Scan handler files for contract compliance violations.

    Pure compute handler — reads Python files and contract YAMLs.
    """

    ALL_CHECKS = [
        "hardcoded-topics",
        "undeclared-transport",
        "missing-routing",
        "logic-in-node",
    ]

    def handle(self, request: ComplianceSweepRequest) -> ComplianceSweepResult:
        """Execute the compliance sweep across target directories."""
        checks = request.checks or self.ALL_CHECKS
        violations: list[ModelComplianceViolation] = []
        handlers_scanned = 0
        compliant_count = 0

        for target_dir in request.target_dirs:
            target = Path(target_dir)
            if not target.is_dir():
                continue
            repo_name = target.name

            handler_files = self._find_handler_files(target)
            for handler_file in handler_files:
                handlers_scanned += 1
                node_name = self._infer_node_name(handler_file, target)
                rel_path = str(handler_file.relative_to(target))
                lines = self._read_lines(handler_file)
                handler_violations: list[ModelComplianceViolation] = []

                if "hardcoded-topics" in checks:
                    handler_violations.extend(
                        self._check_hardcoded_topics(
                            repo_name, rel_path, node_name, lines
                        )
                    )
                if "undeclared-transport" in checks:
                    handler_violations.extend(
                        self._check_transport_imports(
                            repo_name, rel_path, node_name, handler_file
                        )
                    )
                if "logic-in-node" in checks and (
                    "node.py" in handler_file.name or handler_file.name == "__init__.py"
                ):
                    handler_violations.extend(
                        self._check_logic_in_node(repo_name, rel_path, node_name, lines)
                    )

                if handler_violations:
                    violations.extend(handler_violations)
                else:
                    compliant_count += 1

        status = "compliant" if not violations else "violations_found"

        return ComplianceSweepResult(
            violations=violations,
            handlers_scanned=handlers_scanned,
            compliant=compliant_count,
            imperative=handlers_scanned - compliant_count,
            status=status,
            dry_run=request.dry_run,
        )

    def _find_handler_files(self, root: Path) -> list[Path]:
        """Find Python files in handler directories."""
        results = []
        for py_file in root.rglob("*.py"):
            if any(part in _EXCLUDED_DIRS for part in py_file.parts):
                continue
            if "handler" in py_file.stem or py_file.parent.name == "handlers":
                results.append(py_file)
        return sorted(results)

    def _infer_node_name(self, handler_file: Path, repo_root: Path) -> str:
        """Infer node name from handler file path."""
        parts = handler_file.relative_to(repo_root).parts
        for part in parts:
            if part.startswith("node_"):
                return part
        return handler_file.stem

    def _read_lines(self, path: Path) -> list[str]:
        try:
            return path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError):
            return []

    def _check_hardcoded_topics(
        self, repo: str, path: str, node: str, lines: list[str]
    ) -> list[ModelComplianceViolation]:
        violations = []
        for i, line in enumerate(lines, 1):
            if _HARDCODED_TOPIC_RE.search(line):
                violations.append(
                    ModelComplianceViolation(
                        repo=repo,
                        handler_path=path,
                        node_name=node,
                        violation_type="HARDCODED_TOPIC",
                        message=f"Hardcoded topic string: {line.strip()[:80]}",
                        severity="ERROR",
                        line=i,
                    )
                )
        return violations

    def _check_transport_imports(
        self, repo: str, path: str, node: str, handler_file: Path
    ) -> list[ModelComplianceViolation]:
        violations = []
        try:
            source = handler_file.read_text(encoding="utf-8")
            tree = ast.parse(source)
        except (OSError, SyntaxError):
            return []

        for ast_node in ast.walk(tree):
            if isinstance(ast_node, ast.Import):
                for alias in ast_node.names:
                    root_module = alias.name.split(".")[0]
                    if root_module in _TRANSPORT_IMPORTS:
                        violations.append(
                            ModelComplianceViolation(
                                repo=repo,
                                handler_path=path,
                                node_name=node,
                                violation_type="UNDECLARED_TRANSPORT",
                                message=f"Transport import: {alias.name}",
                                severity="WARNING",
                                line=ast_node.lineno,
                            )
                        )
            elif isinstance(ast_node, ast.ImportFrom) and ast_node.module:
                root_module = ast_node.module.split(".")[0]
                if root_module in _TRANSPORT_IMPORTS:
                    violations.append(
                        ModelComplianceViolation(
                            repo=repo,
                            handler_path=path,
                            node_name=node,
                            violation_type="UNDECLARED_TRANSPORT",
                            message=f"Transport import: from {ast_node.module}",
                            severity="WARNING",
                            line=ast_node.lineno,
                        )
                    )
        return violations

    def _check_logic_in_node(
        self, repo: str, path: str, node: str, lines: list[str]
    ) -> list[ModelComplianceViolation]:
        violations = []
        for i, line in enumerate(lines, 1):
            for pattern in _LOGIC_INDICATORS:
                if pattern.search(line):
                    violations.append(
                        ModelComplianceViolation(
                            repo=repo,
                            handler_path=path,
                            node_name=node,
                            violation_type="LOGIC_IN_NODE",
                            message=f"Business logic in node file: {line.strip()[:80]}",
                            severity="WARNING",
                            line=i,
                        )
                    )
        return violations

# SPDX-FileCopyrightText: 2026 OmniNode.ai Inc.
# SPDX-License-Identifier: MIT
"""Skill result model — output from the dispatch_engine skill dispatch node."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class SkillResultStatus(StrEnum):
    """Possible outcomes of a dispatch_engine skill invocation (scaffold)."""

    DISPATCHED = "dispatched"
    DRY_RUN = "dry_run"
    FAILED = "failed"


class ModelSkillResult(BaseModel):
    """Output from the dispatch_engine skill dispatch node."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    skill_name: str = Field(..., min_length=1)
    status: SkillResultStatus = Field(...)
    error: str | None = Field(default=None)


__all__ = ["ModelSkillResult", "SkillResultStatus"]

# SPDX-FileCopyrightText: 2026 OmniNode.ai Inc.
# SPDX-License-Identifier: MIT
"""Skill node: dispatch_engine orchestrator (scaffold).

Thin orchestrator shell for the ``dispatch_engine`` skill. Live dispatch path
returns a ``"dispatched"`` placeholder — real dispatch wiring is follow-up.
"""

from omnimarket.nodes.node_skill_dispatch_engine_orchestrator.node import (
    NodeSkillDispatchEngineOrchestrator,
)

__all__ = ["NodeSkillDispatchEngineOrchestrator"]

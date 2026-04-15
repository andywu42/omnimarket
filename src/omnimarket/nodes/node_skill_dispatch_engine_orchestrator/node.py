# SPDX-FileCopyrightText: 2026 OmniNode.ai Inc.
# SPDX-License-Identifier: MIT
"""NodeSkillDispatchEngineOrchestrator — thin orchestrator shell for dispatch_engine.

Capability: skill.dispatch_engine

Scaffold: live dispatch returns a ``"dispatched"`` placeholder. Real wiring to
the polymorphic agent is follow-up work (tracked alongside OMN-8821).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from omnibase_core.nodes.node_orchestrator import NodeOrchestrator

if TYPE_CHECKING:
    from omnibase_core.models.container.model_onex_container import ModelONEXContainer


class NodeSkillDispatchEngineOrchestrator(NodeOrchestrator):
    """Orchestrator node for the dispatch_engine skill.

    Capability: skill.dispatch_engine

    All behavior defined in ``contract.yaml``. Dispatch logic lives in
    ``HandlerSkillRequested``. This node is a thin coordination shell.
    """

    def __init__(self, container: ModelONEXContainer) -> None:
        super().__init__(container)


__all__ = ["NodeSkillDispatchEngineOrchestrator"]

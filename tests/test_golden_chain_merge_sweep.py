"""Golden chain test for node_merge_sweep.

Verifies PR classification logic and event bus wiring.
"""

from __future__ import annotations

import json

import pytest
from omnibase_core.event_bus.event_bus_inmemory import EventBusInmemory

from omnimarket.nodes.node_merge_sweep.handlers.handler_merge_sweep import (
    MergeSweepRequest,
    NodeMergeSweep,
    PRInfo,
    PRTrack,
)

CMD_TOPIC = "onex.cmd.market.merge-sweep-requested.v1"
EVT_TOPIC = "onex.evt.market.merge-sweep-completed.v1"


@pytest.mark.unit
class TestMergeSweepGoldenChain:
    """Golden chain: command -> classify -> completion event."""

    async def test_merge_ready_pr_classified_track_a(
        self, event_bus: EventBusInmemory
    ) -> None:
        """A mergeable, green, approved PR should go to Track A."""
        handler = NodeMergeSweep()
        pr = PRInfo(
            number=42,
            title="feat: add feature",
            repo="OmniNode-ai/omniclaude",
            mergeable="MERGEABLE",
            merge_state_status="CLEAN",
            review_decision="APPROVED",
            required_checks_pass=True,
        )
        request = MergeSweepRequest(prs=[pr])
        result = handler.handle(request)

        assert result.status == "queued"
        assert len(result.track_a_merge) == 1
        assert result.track_a_merge[0].pr.number == 42

    async def test_behind_pr_classified_track_a_update(
        self, event_bus: EventBusInmemory
    ) -> None:
        """A mergeable but BEHIND PR should go to Track A-update."""
        handler = NodeMergeSweep()
        pr = PRInfo(
            number=10,
            title="fix: typo",
            repo="OmniNode-ai/omnibase_core",
            mergeable="MERGEABLE",
            merge_state_status="BEHIND",
            review_decision="APPROVED",
            required_checks_pass=True,
        )
        request = MergeSweepRequest(prs=[pr])
        result = handler.handle(request)

        assert len(result.track_a_update) == 1
        assert result.track_a_update[0].track == PRTrack.A_UPDATE

    async def test_conflicting_pr_classified_track_b(
        self, event_bus: EventBusInmemory
    ) -> None:
        """A conflicting PR should go to Track B for polish."""
        handler = NodeMergeSweep()
        pr = PRInfo(
            number=99,
            title="chore: update deps",
            repo="OmniNode-ai/omnidash",
            mergeable="CONFLICTING",
            merge_state_status="DIRTY",
            review_decision="APPROVED",
            required_checks_pass=True,
        )
        request = MergeSweepRequest(prs=[pr])
        result = handler.handle(request)

        assert len(result.track_b_polish) == 1
        assert "conflicts" in result.track_b_polish[0].reason

    async def test_draft_pr_skipped(self, event_bus: EventBusInmemory) -> None:
        """Draft PRs should be skipped."""
        handler = NodeMergeSweep()
        pr = PRInfo(
            number=5,
            title="wip: new feature",
            repo="OmniNode-ai/omniclaude",
            mergeable="MERGEABLE",
            merge_state_status="CLEAN",
            is_draft=True,
        )
        request = MergeSweepRequest(prs=[pr])
        result = handler.handle(request)

        assert result.status == "nothing_to_merge"
        assert len(result.skipped) == 1

    async def test_max_total_merges_cap(self, event_bus: EventBusInmemory) -> None:
        """max_total_merges should cap Track A candidates."""
        handler = NodeMergeSweep()
        prs = [
            PRInfo(
                number=i,
                title=f"PR #{i}",
                repo="OmniNode-ai/test",
                mergeable="MERGEABLE",
                merge_state_status="CLEAN",
                review_decision="APPROVED",
                required_checks_pass=True,
            )
            for i in range(5)
        ]
        request = MergeSweepRequest(prs=prs, max_total_merges=2)
        result = handler.handle(request)

        assert len(result.track_a_merge) == 2
        assert len(result.skipped) == 3

    async def test_skip_polish_flag(self, event_bus: EventBusInmemory) -> None:
        """--skip-polish should move Track B PRs to skip."""
        handler = NodeMergeSweep()
        pr = PRInfo(
            number=77,
            title="fix: broken",
            repo="OmniNode-ai/test",
            mergeable="CONFLICTING",
            merge_state_status="DIRTY",
        )
        request = MergeSweepRequest(prs=[pr], skip_polish=True)
        result = handler.handle(request)

        assert len(result.track_b_polish) == 0
        assert len(result.skipped) == 1

    async def test_event_bus_wiring(self, event_bus: EventBusInmemory) -> None:
        """Handler can be wired to event bus for command/completion flow."""
        handler = NodeMergeSweep()
        completions: list[dict[str, object]] = []

        async def on_command(message: object) -> None:
            payload = json.loads(message.value)
            prs = [PRInfo(**pr_data) for pr_data in payload.get("prs", [])]
            request = MergeSweepRequest(prs=prs)
            result = handler.handle(request)
            completion = {
                "status": result.status,
                "track_a": len(result.track_a_merge),
                "track_b": len(result.track_b_polish),
            }
            completions.append(completion)
            await event_bus.publish(
                EVT_TOPIC,
                key=None,
                value=json.dumps(completion).encode(),
            )

        await event_bus.start()
        await event_bus.subscribe(
            CMD_TOPIC, on_message=on_command, group_id="test-merge"
        )

        cmd_payload = json.dumps(
            {
                "prs": [
                    {
                        "number": 1,
                        "title": "test",
                        "repo": "test/repo",
                        "mergeable": "MERGEABLE",
                        "merge_state_status": "CLEAN",
                        "review_decision": "APPROVED",
                        "required_checks_pass": True,
                    }
                ]
            }
        ).encode()
        await event_bus.publish(CMD_TOPIC, key=None, value=cmd_payload)

        assert len(completions) == 1
        assert completions[0]["status"] == "queued"
        assert completions[0]["track_a"] == 1

        history = await event_bus.get_event_history(topic=EVT_TOPIC)
        assert len(history) == 1

        await event_bus.close()

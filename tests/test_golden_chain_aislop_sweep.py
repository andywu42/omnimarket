"""Golden chain test for node_aislop_sweep.

Verifies the handler can be wired to EventBusInmemory, receive a command
event, execute the scan, and emit a completion event.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest
from omnibase_core.event_bus.event_bus_inmemory import EventBusInmemory

from omnimarket.nodes.node_aislop_sweep.handlers.handler_aislop_sweep import (
    AislopSweepRequest,
    NodeAislopSweep,
)

CMD_TOPIC = "onex.cmd.omnimarket.aislop-sweep-start.v1"
EVT_TOPIC = "onex.evt.omnimarket.aislop-sweep-completed.v1"


@pytest.mark.unit
class TestAislopSweepGoldenChain:
    """Golden chain: command -> handler -> completion event."""

    async def test_clean_repo_produces_clean_result(
        self, event_bus: EventBusInmemory
    ) -> None:
        """A repo with no anti-patterns should produce status=clean."""
        handler = NodeAislopSweep()

        with tempfile.TemporaryDirectory() as tmpdir:
            src_dir = Path(tmpdir) / "src"
            src_dir.mkdir()
            (src_dir / "clean.py").write_text("def hello():\n    return 42\n")

            request = AislopSweepRequest(target_dirs=[tmpdir])
            result = handler.handle(request)

        assert result.status == "clean"
        assert result.total_findings == 0
        assert result.repos_scanned == 1

    async def test_prohibited_pattern_detected(
        self, event_bus: EventBusInmemory
    ) -> None:
        """Prohibited env var patterns should be flagged as CRITICAL."""
        handler = NodeAislopSweep()

        with tempfile.TemporaryDirectory() as tmpdir:
            src_dir = Path(tmpdir) / "src"
            src_dir.mkdir()
            (src_dir / "bad.py").write_text('ONEX_EVENT_BUS_TYPE = "inmemory"\n')

            request = AislopSweepRequest(
                target_dirs=[tmpdir], checks=["prohibited-patterns"]
            )
            result = handler.handle(request)

        assert result.status == "findings"
        assert result.total_findings >= 1
        assert result.by_severity.get("CRITICAL", 0) >= 1
        assert result.by_check.get("prohibited-patterns", 0) >= 1

    async def test_hardcoded_topic_detected(self, event_bus: EventBusInmemory) -> None:
        """Hardcoded topic strings in src/ should be flagged as ERROR."""
        handler = NodeAislopSweep()

        with tempfile.TemporaryDirectory() as tmpdir:
            src_dir = Path(tmpdir) / "src"
            src_dir.mkdir()
            (src_dir / "topics.py").write_text('TOPIC = "onex.evt.core.something.v1"\n')

            request = AislopSweepRequest(
                target_dirs=[tmpdir], checks=["hardcoded-topics"]
            )
            result = handler.handle(request)

        assert result.status == "findings"
        assert result.total_findings >= 1

    async def test_event_bus_wiring(self, event_bus: EventBusInmemory) -> None:
        """Handler can be wired to event bus and process command events."""
        handler = NodeAislopSweep()
        results_captured: list[dict[str, object]] = []

        async def on_command(message: object) -> None:
            payload = json.loads(message.value)
            request = AislopSweepRequest(
                target_dirs=payload.get("target_dirs", []),
                checks=payload.get("checks"),
            )
            result = handler.handle(request)
            result_payload = {
                "status": result.status,
                "total_findings": result.total_findings,
                "repos_scanned": result.repos_scanned,
            }
            results_captured.append(result_payload)
            await event_bus.publish(
                EVT_TOPIC,
                key=None,
                value=json.dumps(result_payload).encode(),
            )

        await event_bus.start()
        await event_bus.subscribe(
            CMD_TOPIC, on_message=on_command, group_id="test-aislop"
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            src_dir = Path(tmpdir) / "src"
            src_dir.mkdir()
            (src_dir / "ok.py").write_text("x = 1\n")

            cmd_payload = json.dumps({"target_dirs": [tmpdir]}).encode()
            await event_bus.publish(CMD_TOPIC, key=None, value=cmd_payload)

        assert len(results_captured) == 1
        assert results_captured[0]["status"] == "clean"

        history = await event_bus.get_event_history(topic=EVT_TOPIC)
        assert len(history) == 1

        await event_bus.close()

    async def test_todo_detection(self, event_bus: EventBusInmemory) -> None:
        """TODO markers in src/ should be flagged."""
        handler = NodeAislopSweep()

        with tempfile.TemporaryDirectory() as tmpdir:
            src_dir = Path(tmpdir) / "src"
            src_dir.mkdir()
            (src_dir / "wip.py").write_text("# TODO: fix this later\nx = 1\n")

            request = AislopSweepRequest(target_dirs=[tmpdir], checks=["todo-fixme"])
            result = handler.handle(request)

        assert result.status == "findings"
        assert result.by_check.get("todo-fixme", 0) >= 1

    async def test_selective_checks(self, event_bus: EventBusInmemory) -> None:
        """Only specified checks should run."""
        handler = NodeAislopSweep()

        with tempfile.TemporaryDirectory() as tmpdir:
            src_dir = Path(tmpdir) / "src"
            src_dir.mkdir()
            (src_dir / "mixed.py").write_text(
                '# TODO fix\nONEX_EVENT_BUS_TYPE = "inmemory"\n'
            )

            # Only check todos, not prohibited patterns
            request = AislopSweepRequest(target_dirs=[tmpdir], checks=["todo-fixme"])
            result = handler.handle(request)

        assert "prohibited-patterns" not in result.by_check
        assert result.by_check.get("todo-fixme", 0) >= 1

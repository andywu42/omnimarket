# CLAUDE.md - OmniMarket

> **Python**: 3.12+ | **Package Manager**: uv | **Shared Standards**: See **`~/.claude/CLAUDE.md`** for shared development standards (Python, Git, testing, architecture principles) and infrastructure configuration.

---

## What This Repo Is

OmniMarket is the **Universal ONEX Workflow Package Registry** -- portable contract packages (`.oncp`) for deterministic skill execution. It converts platform-specific AI coding skills (currently 100+ markdown files in omniclaude) into ONEX contract packages executable via RuntimeLocal with zero infrastructure.

**Design doc**: `/Volumes/PRO-G40/Code/omni_home/docs/plans/2026-04-05-omnimarket-design.md`

---

## Architecture

### Four Layers

| Layer | Definition | Example |
|-------|-----------|---------|
| **SkillSurface** | Platform-specific invocation wrapper (thin, no logic) | `omniclaude/plugins/onex/skills/aislop_sweep/SKILL.md` |
| **NodeUnit** | Single ONEX contract unit: `contract.yaml` + handler(s) | `node_aislop_sweep` |
| **WorkflowPackage** | Composed NodeUnits with internal event routing | `node_ticket_pipeline` |
| **MarketArtifact (.oncp)** | Installable distribution: archive with metadata, contracts, handlers, tests | `node_aislop_sweep-1.0.0.oncp` |

**Key rule:** Wrappers do not own business logic. They translate platform UX into package command events and render results back.

### Execution Modes

- **Standalone** (no infra): `uv run onex run node_aislop_sweep -- --dry-run --repos omniclaude` -- uses RuntimeLocal + EventBusInmemory
- **Full stack**: Same contract, same handlers, events route through Redpanda on .201

### Topic Naming Convention

`onex.{cmd|evt}.omnimarket.{event-name}.v{N}`

Topics are declared in each node's `contract.yaml` -- never hardcoded in handler code.

---

## Repo Invariants

- **Handlers own logic** -- nodes are thin coordination shells
- **Contracts are source of truth** -- YAML contracts define topics, inputs, outputs
- **Every node must have golden chain tests** -- EventBusInmemory, zero infra required
- **Entry points resolve to package directories** containing `contract.yaml`, not factory callables
- **`metadata.yaml` in every node** -- declares capabilities, dependencies, compatibility

---

## Quick Reference

```bash
# Setup
uv sync --all-extras

# Testing
uv run pytest tests/ -v                # All tests
uv run pytest tests/ -m unit            # Unit tests only

# Code Quality
uv run mypy src/omnimarket/ --strict    # Type checking
uv run ruff check src/ tests/           # Linting
uv run ruff format src/ tests/          # Formatting

# Run a node standalone (once RuntimeLocal wiring is complete)
uv run onex run node_aislop_sweep -- --dry-run
```

---

## Project Structure

```
src/omnimarket/
  __init__.py
  models/                    # Pydantic models (metadata schema, etc.)
  nodes/
    node_aislop_sweep/       # AI slop detection sweep
      contract.yaml          # Topics, inputs, outputs
      metadata.yaml          # .oncp metadata (capabilities, deps)
      handlers/              # Business logic
      tests/                 # Node-local tests (optional)
    node_merge_sweep/        # Org-wide PR sweep
    node_platform_readiness/ # Platform readiness gate
  adapters/
    claude_code/             # SKILL.md wrapper templates
    cursor/                  # .mdc wrapper templates
    codex/                   # Codex instruction templates
tests/
  conftest.py                # Shared EventBusInmemory fixtures
  test_golden_chain_*.py     # Golden chain tests per node
```

---

## Adding a New Node

1. Create `src/omnimarket/nodes/node_{name}/` with `__init__.py`, `contract.yaml`, `metadata.yaml`, `handlers/__init__.py`
2. Define topics in `contract.yaml` following `onex.{cmd|evt}.omnimarket.{name}.v{N}`
3. Write handler logic in `handlers/handler_{name}.py`
4. Add golden chain test in `tests/test_golden_chain_{name}.py`
5. Register entry point in `pyproject.toml` under `[project.entry-points."onex.nodes"]`

---

## Dependencies

- **omnibase_core** (editable, path-linked in dev): Contract system, EventBusInmemory, RuntimeLocal
- **pydantic**: Typed models
- **pyyaml**: Contract/metadata parsing

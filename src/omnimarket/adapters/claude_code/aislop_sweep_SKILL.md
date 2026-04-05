---
description: Detect AI-generated quality anti-patterns across repos via OmniMarket aislop-sweep node.
version: 1.0.0
mode: full
level: advanced
debug: false
category: quality
tags:
  - ai-quality
  - code-review
  - anti-patterns
  - omnimarket
author: OmniMarket
composable: true
args:
  - name: --repos
    description: "Comma-separated repo names to scan (default: all supported repos)"
    required: false
  - name: --checks
    description: "Comma-separated pattern categories: phantom-callables,compat-shims,prohibited-patterns,hardcoded-topics,todo-fixme,todo-stale,empty-impls (default: all)"
    required: false
  - name: --dry-run
    description: Scan and report only — no tickets, no fixes
    required: false
  - name: --ticket
    description: Create Linear tickets for findings above severity threshold
    required: false
  - name: --auto-fix
    description: Attempt auto-fix for trivially fixable patterns
    required: false
  - name: --severity-threshold
    description: "Minimum severity to act on: WARNING | ERROR (default: WARNING)"
    required: false
inputs:
  - name: repos
    description: "list[str] — repos to scan; empty = all"
outputs:
  - name: skill_result
    description: "Completion event payload with status: clean | findings | partial | error"
---

# AI Slop Sweep (OmniMarket)

## Overview

Thin event-bus wrapper around the OmniMarket `aislop_sweep` node. This skill
publishes a command event and monitors for completion — all business logic
executes in the node handler.

**Announce at start:** "Running aislop-sweep via OmniMarket event bus."

## Execution

### Step 1 — Assemble payload

Collect arguments from the user invocation and build the command payload:

```json
{
  "correlation_id": "<uuid4>",
  "repos": ["omniclaude", "omnibase_core"],
  "checks": ["phantom-callables", "todo-fixme"],
  "dry_run": true,
  "ticket": false,
  "auto_fix": false,
  "severity_threshold": "WARNING"
}
```

Omit fields the user did not specify — the node applies its own defaults.

### Step 2 — Publish command event

Publish to topic: `onex.cmd.market.aislop-sweep-requested.v1`

### Step 3 — Monitor completion

Listen on topic: `onex.evt.market.aislop-sweep-completed.v1`

Filter by `correlation_id`. Timeout: **120000 ms** (from contract `descriptor.timeout_ms`).

### Step 4 — Format output

On success, render the completion payload as a findings summary table grouped by
severity and check category. On timeout or error, report the failure clearly.

## CLI

```
/aislop-sweep                                    # Full scan all repos
/aislop-sweep --dry-run                          # Report only
/aislop-sweep --ticket                           # Create Linear tickets
/aislop-sweep --checks phantom-callables,todo-fixme
/aislop-sweep --repos omniclaude,omnibase_core
/aislop-sweep --auto-fix                         # Fix trivial patterns
```

## Important

This wrapper contains **no business logic**. Do not add scanning, triaging,
or ticket-creation logic here. All of that is handled by the
`aislop_sweep` node in `omnimarket/nodes/node_aislop_sweep/`.

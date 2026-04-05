# Codex Adapter — OmniMarket

## Overview

Codex adapters are instruction files that tell the OpenAI Codex agent how to
invoke OmniMarket packages via the ONEX event bus. Each instruction file
describes the event-publish/monitor pattern for a single node. **No business
logic lives in the instruction file.**

## How it works

1. The Codex agent reads the instruction file as part of its system context
2. When the user requests the relevant operation, the agent publishes a command event
3. The OmniMarket node picks up the command, executes, and publishes a completion event
4. The agent monitors for the completion event and formats the result

## File conventions

| File | Purpose |
|------|---------|
| `aislop-sweep-instructions.md` | Example instructions for the aislop-sweep node |
| `template.md` | Generic template with placeholders for new instructions |

Instructions are provided to Codex via its instruction/system prompt configuration.

## Wrapper responsibilities

1. **Argument collection and validation** — Parse user-provided arguments and map
   them to the event payload schema from `contract.yaml`.
2. **Command options mapping** — Translate arguments into the structured event
   payload fields expected by the node.
3. **Correlation ID generation** — Generate a unique `correlation_id` (UUID v4) for
   each invocation to track request/response pairs on the bus.
4. **Event publishing** — Publish the command event to the node's `subscribe_topics`
   topic with the assembled payload and correlation ID.
5. **Completion monitoring** — Listen on the node's `publish_topics` topic, filtering
   by correlation ID, with a configurable timeout.
6. **Output formatting** — Transform the completion event payload into a clear
   response for the user.
7. **Timeout and error handling** — If no completion event arrives within the node's
   `descriptor.timeout_ms`, report a timeout error. Surface any error payloads
   from the completion event clearly.

## Creating new instructions

1. Copy `template.md` to `<skill-name>-instructions.md`
2. Replace all `{{PLACEHOLDER}}` values using the node's `contract.yaml`
3. Add the resulting file to your Codex agent's instruction configuration

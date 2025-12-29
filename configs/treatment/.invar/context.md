# Benchmark Task Context

*Template for benchmark tasks - populated by harness*

## Key Rules (Quick Reference)

### Core/Shell Separation
- **Core** (`**/core/**`): @pre/@post + doctests, NO I/O imports
- **Shell** (`**/shell/**`): Result[T, E] return type

### USBV Workflow
1. Understand → 2. Specify (contracts first) → 3. Build → 4. Validate

### Verification
- `invar guard` = static + doctests + CrossHair + Hypothesis
- Final must show: `✓ Final: guard PASS | ...`

## Task Router (DX-62)

| If you are about to... | STOP and read first |
|------------------------|---------------------|
| Write code in `core/` | `.invar/examples/contracts.py` |
| Write code in `shell/` | `.invar/examples/core_shell.py` |
| Add `@pre`/`@post` contracts | `.invar/examples/contracts.py` |
| Use functional patterns | `.invar/examples/functional.py` |
| Implement a feature | `.invar/examples/workflow.md` |

**Rule:** Match found above? Read the file BEFORE writing code.

## Self-Reminder

**When to re-read this file:**
- Starting a new task
- Completing a task (before moving to next)
- Conversation has been going on for a while (~15-20 exchanges)
- Unsure about project rules or patterns

**Quick rule check:**
- Am I in Core or Shell?
- Do I have @pre/@post contracts?
- Am I following USBV workflow?
- Did I run guard before claiming "done"?

---

## Current State

- **Task:** {{TASK_NAME}}
- **Description:** {{TASK_DESCRIPTION}}
- **Status:** In Progress
- **Blockers:** None

## Task Requirements

{{TASK_REQUIREMENTS}}

---

## Tool Priority

| Task | Primary | Fallback |
|------|---------|----------|
| See contracts | `invar sig` | — |
| Find entry points | `invar map --top` | — |
| Verify | `invar guard` | — |

---

*This file is populated by the benchmark harness for each task.*

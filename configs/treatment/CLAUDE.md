<!--invar:critical-->
## ⚡ Critical Rules

| Always | Remember |
|--------|----------|
| **Verify** | `invar_guard` — NOT pytest, NOT crosshair |
| **Core** | `@pre/@post` + doctests, NO I/O imports |
| **Shell** | Returns `Result[T, E]` from `returns` library |
| **Flow** | USBV: Understand → Specify → Build → Validate |

<!--/invar:critical--><!--invar:managed version="5.0"-->
# Project Development Guide

> **Protocol:** Follow [INVAR.md](./INVAR.md) — includes Check-In, USBV workflow, and Task Completion requirements.

## Check-In (DX-54)

Your first message MUST display:

```
✓ Check-In: [project] | [branch] | [clean/dirty]
```

Actions:
1. Read `.invar/context.md` (Key Rules + Current State + Lessons Learned)
2. Show one-line status

Example:
```
✓ Check-In: MyProject | main | clean
```

**Do NOT execute guard or map at Check-In.**
Guard is for VALIDATE phase and Final only.

This is your sign-in. The user sees it immediately.
No visible check-in = Session not started.

---

## Final

Your last message for an implementation task MUST display:

```
✓ Final: guard PASS | 0 errors, 2 warnings
```

Execute `invar_guard()` and show this one-line summary.


This is your sign-out. Completes the Check-In/Final pair.

---

## Project Structure

```
src/{project}/
├── core/    # Pure logic (@pre/@post, doctests, no I/O)
└── shell/   # I/O operations (Result[T, E] return type)
```

**Key insight:** Core receives data (strings), Shell handles I/O (paths, files).

## Quick Reference

| Zone | Requirements |
|------|-------------|
| Core | `@pre`/`@post` + doctests, pure (no I/O) |
| Shell | Returns `Result[T, E]` from `returns` library |

## Documentation Structure

| File | Owner | Edit? | Purpose |
|------|-------|-------|---------|
| INVAR.md | Invar | No | Protocol (`invar update` to sync) |
| CLAUDE.md | User | Yes | Project customization (this file) |
| .invar/context.md | User | Yes | Project state, lessons learned |
| .invar/project-additions.md | User | Yes | Project rules → injected into CLAUDE.md |
| .invar/examples/ | Invar | No | **Must read:** Core/Shell patterns, workflow |

## Visible Workflow (DX-30)

For complex tasks (3+ functions), show 3 checkpoints in TodoList:

```
□ [UNDERSTAND] Task description, codebase context, constraints
□ [SPECIFY] Contracts (@pre/@post) and design decomposition
□ [VALIDATE] Guard results, Review Gate status, integration status
```

**BUILD is internal work** — not shown in TodoList.

**Show contracts before code.** See `.invar/examples/workflow.md` for full example.

## Phase Visibility (DX-51)

Each USBV phase transition requires a visible header:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📍 /develop → SPECIFY (2/4)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

**Three-layer visibility:**
- **Skill** (`/develop`) — Routing announcement
- **Phase** (`SPECIFY 2/4`) — Phase header (this section)
- **Tasks** — TodoWrite items

Phase headers are SEPARATE from TodoWrite. Phase = where you are; TodoWrite = what to do.

---

## Context Management (DX-54)

Re-read `.invar/context.md` when:
1. Entering any workflow (/develop, /review, etc.)
2. Completing a TodoWrite task (before moving to next)
3. Conversation exceeds ~15-20 exchanges
4. Unsure about project rules or patterns

**Refresh is transparent** — do not announce "I'm refreshing context."
Only show routing announcements when entering workflows.

---

## Commands (User-Invokable)

| Command | Purpose |
|---------|---------|
| `/audit` | Read-only code review (reports issues, no fixes) |
| `/guard` | Run Invar verification (reports results) |

## Skills (Agent-Invoked)

| Skill | Triggers | Purpose |
|-------|----------|---------|
| `/investigate` | "why", "explain", vague tasks | Research mode, no code changes |
| `/propose` | "should we", "compare" | Decision facilitation |
| `/develop` | "add", "fix", "implement" | USBV implementation workflow |
| `/review` | After /develop, `review_suggested` | Adversarial review with fix loop |

**Note:** Skills are invoked by agent based on context. Use `/audit` for user-initiated review.

Guard triggers `review_suggested` for: security-sensitive files, escape hatches >= 3, contract coverage < 50%.

---

## Workflow Routing (MANDATORY)

When user message contains these triggers, you MUST use the **Skill tool** to invoke the skill:

| Trigger Words | Skill Tool Call | Notes |
|---------------|-----------------|-------|
| "review", "review and fix" | `Skill(skill="review")` | Adversarial review with fix loop |
| "implement", "add", "fix", "update" | `Skill(skill="develop")` | Unless in review context |
| "why", "explain", "investigate" | `Skill(skill="investigate")` | Research mode, no code changes |
| "compare", "should we", "design" | `Skill(skill="propose")` | Decision facilitation |

**⚠️ CRITICAL: You must call the Skill tool, not just follow the workflow mentally.**

The Skill tool reads `.claude/skills/<skill>/SKILL.md` which contains:
- Detailed phase instructions (USBV breakdown)
- Error handling rules
- Timeout policies
- Incremental development patterns (DX-63)

**Violation check (before writing ANY code):**
- "Did I call `Skill(skill="...")`?"
- "Am I following the SKILL.md instructions?"

---

## Routing Control (DX-42)

Agent announces routing decision before entering any workflow:

```
📍 Routing: /[skill] — [trigger or reason]
   Task: [summary]
```

**User can redirect with natural language:**
- "wait" / "stop" — pause and ask for direction
- "just do it" — proceed with /develop
- "let's discuss" — switch to /propose
- "explain first" — switch to /investigate

**Simple task optimization:** For simple tasks (single file, clear target, <50 lines), agent may offer:

```
📊 Simple task. Auto-orchestrate? [Y/N]
```

- Y → Full cycle without intermediate confirmations
- N → Normal step-by-step workflow

**Auto-review (DX-41):** When Guard outputs `review_suggested`, agent automatically
enters /review. Say "skip" to bypass.
<!--/invar:managed--><!--invar:project-->
## Benchmark Task Project

This is a benchmark task for testing the Invar framework with Claude Code.

### Project Structure

```
src/
├── core/    # Pure logic, @pre/@post required, no I/O
└── shell/   # I/O operations, Result[T, E] required
```

### Rules

1. **Language:** English for docs/code.
2. **Verify Always:** Run `invar_guard()` after changes.
3. **Warning Policy:** Fix warnings in files you modify.

### Dependencies

```bash
pip install deal returns invar-runtime
```

<!--/invar:project--><!--invar:user-->
<!-- ========================================================================
     USER REGION - EDITABLE
     Add your team conventions and project-specific rules below.
     This section is preserved across invar update and sync-self.
     ======================================================================== -->
<!--/invar:user-->

---

*Invar Benchmark - Treatment Group Configuration v5.0*

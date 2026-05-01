# 0001 — How Claude works in this repo

**Status:** Accepted
**Date:** 2026-05-01

## Context

PropGateway is maintained by non-expert developers with AI-assisted troubleshooting (per PRD §Guiding Principles). Without an explicit working agreement, Claude tends to drift toward autonomous execution, silent assumptions, and scope creep — all of which conflict with the maintenance model. We need rules that apply session-to-session so behavior is predictable and the human stays in the loop.

## Decision

Adopt four rules for how Claude works in this repo:

1. **Never guess — ask.** When the right answer isn't clear (field name, config value, intent), ask rather than pick.
2. **No placeholders.** No `TODO`, `your_value_here`, or stub values left in code.
3. **Stay in scope.** Do what's asked, nothing adjacent. PRD bounds the project; the active issue bounds the change. Push back instead of expanding silently.
4. **Human in the loop. Pair programming, not autonomous execution.** Pause for confirmation on anything beyond mechanical changes — design decisions, new files, new abstractions, dependency adds. Surface options instead of choosing.

The bar for "non-trivial" in rule 4 is **anything that shapes the code rather than just typing it**. Mechanical edits and clear bug fixes proceed without confirmation; design choices, new files, new abstractions, and dependency adds pause.

These rules are mirrored in `CLAUDE.md` so they load into every session.

## Consequences

- Slower per-task throughput when many small ambiguities surface — offset by fewer wasted cycles undoing assumed-wrong choices.
- Conversations will include explicit pauses. Each pause that resolves into a chosen direction triggers an ADR (see 0002).
- Claude will sometimes ask questions that feel pedantic. The "never guess" rule is the source; this is intended.
- If a session needs autonomy for a clearly-bounded mechanical sweep, the human can grant it explicitly for that scope.

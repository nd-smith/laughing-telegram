# 0002 — Use ADRs for design decisions

**Status:** Accepted
**Date:** 2026-05-01

## Context

The "human in the loop" rule (0001) introduces frequent pause-for-confirmation moments where a design direction is chosen. Without persistence, those choices live only in chat history and are lost across sessions. We need a record so that future Claude sessions and human readers can see why the codebase looks the way it does.

## Decision

- Every option-3 pause (per 0001) that resolves into a chosen direction produces an Architecture Decision Record.
- ADRs live at `decisions/NNNN-kebab-case-title.md`, numbered sequentially and zero-padded to four digits.
- Use the standard ADR format with these sections: **Status**, **Date**, **Context**, **Decision**, **Consequences**.
- ADRs reference the originating issue (see 0003) when applicable.
- `decisions/index.md` maintains a chronological index. Entry format:

  ```
  - [Title](NNNN-kebab-case-title.md) {YYYY-MM-DD} — very brief summary
  ```

## Consequences

- Every meaningful pairing decision gets a small written artifact. Overhead per decision, but durable context.
- Future Claude sessions can read `decisions/` to ground themselves on prior choices instead of re-deriving them.
- The index becomes the canonical "what was decided" timeline.
- Risk of ADR proliferation if the bar drifts low. The option-3 definition in 0001 is the gate.

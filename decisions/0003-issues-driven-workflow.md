# 0003 — Issues-driven workflow for pipeline code work

**Status:** Accepted
**Date:** 2026-05-01

## Context

PropGateway code work needs a clear unit of work so that scope is bounded and intent is captured before code is written. We also want decisions (ADRs) to trace back to the work that produced them.

## Decision

- Pipeline code work is triggered by an issue file. No issue → no code work.
- This rule applies to **pipeline code work** (`pipeline/`, `shared/`, `tests/`). It does **not** apply to repo bootstrapping or meta-documentation work like setting up `CLAUDE.md`, `decisions/`, or `issues/` themselves.
- Issues live at `issues/NNNN_snake_case_title.md`, numbered sequentially and zero-padded to four digits.
- Issues are created **collaboratively** — sometimes drafted from discussion, sometimes written directly.
- ADRs produced during work on an issue reference that issue in their **Context** section.
- The first body of work for the project is breaking the PRD down into issues.

## Consequences

- Casual "just go fix this" code requests get redirected into an issue first. Some friction up-front; clearer intent and history downstream.
- Issue files and ADRs together form the project's reasoning record: issues describe what we're doing and why; ADRs describe how we chose to do it.
- Bootstrapping work (the current setup of `CLAUDE.md` and these ADRs) intentionally proceeds without an issue, since the workflow itself didn't exist yet.

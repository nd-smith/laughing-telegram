---
description: Work the next active issue (or the one passed as argument) end-to-end per CLAUDE.md workflow.
---

You are starting work on a PropGateway pipeline issue. Follow this workflow exactly. Do not skip steps.

## Argument

`$ARGUMENTS` — optional. May be an issue number (e.g. `0003` or `3`) or a filename in `issues/`. If empty, pick the lowest-numbered active issue.

## 1. Verify clean working state

If the working directory is a git repo, run `git status --porcelain`. If output is non-empty, stop and report the dirty files to the user — do not proceed until the tree is clean. If the directory is not a git repo, skip this check.

## 2. Pick the target issue

- If `$ARGUMENTS` is provided: resolve it. A bare number → find `issues/NNNN_*.md` (zero-pad to 4 digits if needed). A filename → use that file. If the resolved file doesn't exist, or is already under `issues/complete/`, stop and ask.
- Otherwise: list `issues/*.md` excluding `index.md` and the `complete/` subdirectory, sort by leading number, pick the lowest.

## 3. Load context

Read in this exact order:
1. `CLAUDE.md` — working agreements.
2. `docs/PRD.md` — authoritative spec.
3. The target issue file.
4. `decisions/index.md` — skim for ADRs that may bear on this issue, and read any that look directly relevant.

## 4. Confirm before coding

Tell the user:
- The issue number and title.
- Your high-level approach in 2–3 sentences.
- The first decision flagged in the issue's Notes section, if any (e.g. items prefixed "Ask before deciding").

Wait for the user to confirm or redirect before writing any code.

## 5. Work the issue

- Honour the issue's **Scope**, **Out of scope**, and **Acceptance criteria** literally.
- Every "Ask before deciding" item in **Notes** is a hard pause. Surface it as a question and wait for the user's call. Never guess.
- For each non-trivial decision the user resolves, draft an ADR at `decisions/NNNN-kebab-case-title.md` using the standard format (Context / Decision / Consequences). Reference the originating issue inside the ADR. Add an entry to `decisions/index.md`.
- Stay in scope. If a request would go outside the issue or the PRD, push back rather than expand silently.
- No placeholders (no `TODO`, no `your_value_here`, no stub values). If you need a value you don't have, ask.

## 6. Verify

- Run the full test suite: `python -m pytest tests/`. All tests must pass.
- Walk each acceptance-criteria bullet from the issue and confirm it is met. State this explicitly.

## 7. Complete the issue

Per CLAUDE.md §Workflow:
- Move the issue file from `issues/` to `issues/complete/`.
- Update `issues/index.md`:
  - Strikethrough the link text (`~~[NNNN — Title](complete/NNNN_snake_case_title.md)~~`).
  - Change the link target to `complete/...` so it still resolves.
  - Append `{YYYY-MM-DD → YYYY-MM-DD}` (creation date → today's completion date).
  - Append dev notes in square brackets: what was implemented + references to any ADRs produced.

## 8. Summarise

End your turn with:
- A diff summary — one line per file added / modified / deleted.
- The list of ADRs produced, if any (with their numbers and titles).
- The pytest summary line (e.g. `12 passed in 0.34s`).

Stop and ask if anything is unclear. Never guess.

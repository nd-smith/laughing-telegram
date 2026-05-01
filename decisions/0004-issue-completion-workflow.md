# 0004 — Issue completion workflow

**Status:** Accepted
**Date:** 2026-05-01

## Context

ADR-0003 established that pipeline code work is triggered by issue files in `issues/`, but didn't specify what happens when an issue is complete. Without a closure ritual, completed and active issues mix in the same directory, and the project loses a record of what was actually implemented and which ADRs came out of each piece of work.

## Decision

When an issue is complete:

1. Move the file from `issues/NNNN_snake_case_title.md` to `issues/complete/NNNN_snake_case_title.md`.
2. Update its entry in `issues/index.md`:
   - Strikethrough the link (it remains clickable in rendered markdown).
   - Update the link path to `complete/...` so it still resolves after the move.
   - Keep both dates as `{creation_date → completion_date}`.
   - Append dev notes in `[ ... ]` capturing what was implemented and references to any ADRs produced during the work.

Active entry format:

```
- [NNNN — Title](NNNN_snake_case_title.md) {YYYY-MM-DD} — one-line summary
```

Completed entry format:

```
- ~~[NNNN — Title](complete/NNNN_snake_case_title.md)~~ {YYYY-MM-DD → YYYY-MM-DD} [what was implemented; ADR refs]
```

## Consequences

- Active vs. completed issues are visually and physically separated; the top of `issues/` shows current work at a glance.
- The index becomes a project-history log: every line is either active work or a struck-through "this was built" record with implementation notes.
- Completion is a small ritual (move + index edit). A missed step (file moved but index not updated, or vice versa) leaves a broken link, which is an obvious tell.

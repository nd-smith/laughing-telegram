# Decision Index

- [How Claude works in this repo](0001-how-claude-works-in-this-repo.md) {2026-05-01} — working agreement: never guess, no placeholders, stay in scope, human in the loop
- [Use ADRs for design decisions](0002-use-adrs-for-design-decisions.md) {2026-05-01} — every option-3 pause produces an ADR; standard ADR format
- [Issues-driven workflow for pipeline code work](0003-issues-driven-workflow.md) {2026-05-01} — pipeline code work requires an issue file; meta/bootstrap work is exempt
- [Issue completion workflow](0004-issue-completion-workflow.md) {2026-05-01} — move completed issues to issues/complete/; strikethrough index entry with both dates and dev notes
- [Pin dependencies with exact versions](0005-pin-dependencies-with-exact-versions.md) {2026-05-01} — `requirements.txt` uses `==` for reproducible builds; deliberate manual bumps
- [`build_envelope` keyword-only signature](0006-build-envelope-keyword-only-signature.md) {2026-05-01} — nine caller inputs passed as kwargs; rejected positional and dataclass alternatives
- [`validate` returns a `NamedTuple` result](0007-validate-result-is-namedtuple.md) {2026-05-01} — `ValidationResult(ok, reason)` over bare tuple or dataclass

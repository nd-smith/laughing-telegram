# CLAUDE.md

PropGateway is a real-time event-data pipeline. External sources push to per-source Azure Event Hubs; one worker process per source consumes, validates, wraps in a standard envelope, micro-batches Parquet to OneLake (Microsoft Fabric Lakehouse), and publishes to a per-source Kafka topic. Workers run on K8s; horizontal scale = more replicas.

The authoritative spec is [`docs/PRD.md`](docs/PRD.md). Read it before non-trivial work. If code and PRD disagree, surface the conflict — don't silently pick one.

## Guiding principles

1. **Simplicity first.** Choose the simplest solution that's good enough. No abstraction layers, DSLs, or frameworks added without a clear reason.
2. **Optimized for AI-assisted maintenance.** Maintainers are not coding professionals; code is read by humans and AI for troubleshooting. Favor explicit and readable over clever.
3. **Deliberate complexity.** Every piece of complexity must earn its place.

## Hard architectural constraints

- **Sync + threading, not asyncio.** Use sync SDK APIs even when async alternatives exist.
- **Per-source logic is plain Python in `pipeline/sources/<source>.py`.** No YAML/JSON/TOML config DSL for source behavior. Adding a source = adding one `.py` file.
- **One worker process = one source**, selected via `--source` CLI arg. No multi-source orchestration inside a worker.
- **Auth is `DefaultAzureCredential`.** No connection strings, API keys, or SAS tokens in code or config.
- **S3 pre-signed URLs are passed through, never fetched** by the pipeline.

## Scope

In scope: `pipeline/`, `shared/`, `tests/`, `docs/`, `decisions/`, `issues/`.

Out of scope (don't touch without explicit ask): `apps/`, deploy manifests, infra provisioning, CI/CD, integration tests.

## How Claude works in this repo

- **Never guess — ask.** When the right answer isn't clear (field name, config value, intent), ask rather than pick.
- **No placeholders.** No `TODO`, no `your_value_here`, no stub values left in code.
- **Stay in scope.** Do what's asked, nothing adjacent. PRD bounds the project; the active issue bounds the change. If a request goes outside either, push back instead of expanding silently.
- **Human in the loop. Pair programming, not autonomous execution.** Pause for confirmation on anything beyond mechanical changes — design decisions, new files, new abstractions, dependency adds. Surface options instead of choosing.

## Workflow

**Issues are the trigger.** No code work happens without an issue file. Issues live at `issues/NNNN_snake_case_title.md` (zero-padded, sequential). Issues are created collaboratively — sometimes drafted from discussion, sometimes written directly.

**Track issues in `issues/index.md`.** Active entry format:

```
- [NNNN — Title](NNNN_snake_case_title.md) {YYYY-MM-DD} — one-line summary
```

**Completing an issue.** Move the issue file to `issues/complete/`, then update its index entry: strikethrough the link, update the link path to `complete/...` so it still resolves, keep both dates (creation → completion), and append dev notes capturing what was implemented and references to any ADRs produced. Format:

```
- ~~[NNNN — Title](complete/NNNN_snake_case_title.md)~~ {YYYY-MM-DD → YYYY-MM-DD} [what was implemented; ADR refs]
```

**Decisions are documented.** Every pause-for-confirmation that resolves into a chosen direction produces an ADR at `decisions/NNNN-kebab-case-title.md` using the standard ADR format (Context / Decision / Consequences). If the decision came out of an issue, reference that issue in the ADR.

**Update `decisions/index.md` with each new ADR.** Entry format:

```
- [Title](NNNN-kebab-case-title.md) {YYYY-MM-DD} — very brief summary
```

## Repo layout

```
propgateway/
  docs/
    PRD.md               # authoritative spec
  decisions/
    index.md             # ADR index
    NNNN-*.md            # ADRs
  issues/
    index.md             # issue index (active + completed)
    complete/            # completed issues
    NNNN_*.md            # active issues we work from
  pipeline/              # core pipeline (per PRD §Repository Structure)
  shared/                # shared utilities
  tests/                 # unit tests
  apps/                  # out of scope here
```

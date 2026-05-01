# 0005 — Pin dependencies with exact versions

**Status:** Accepted
**Date:** 2026-05-01

## Context

Issue [0001](../issues/complete/0001_project_scaffolding_and_dependencies.md) creates `requirements.txt` with seven packages. The issue's Notes flagged version-pinning style as an "ask before deciding" item. Three options were on the table:

- `==` (exact pin) — fully reproducible, no surprise upgrades, requires deliberate bumps.
- `>=` (lower bound) — flexible but non-reproducible; two installs days apart can produce different envs.
- `~=` (compatible release) — patch updates allowed, minor/major blocked.

PropGateway runs as long-lived workers in K8s. Reproducibility of the deployed image matters more than picking up upstream patches automatically. Maintainers are non-experts and rely on AI-assisted troubleshooting; surprise behavior changes from a transitive upgrade between rebuilds are exactly the kind of thing that's hard to diagnose without expertise.

## Decision

Pin every entry in `requirements.txt` with `==` to a specific stable version. Initial pins use the latest stable release of each package as of 2026-05-01:

- `azure-eventhub==5.15.1`
- `azure-identity==1.25.3`
- `azure-storage-file-datalake==12.23.0`
- `confluent-kafka==2.14.0`
- `pyarrow==24.0.0`
- `prometheus-client==0.25.0`
- `pytest==9.0.3`

Bumps are deliberate edits to `requirements.txt` reviewed like any other code change.

## Consequences

- Reproducible builds: same `requirements.txt` resolves to the same versions every time.
- Security patches and bug fixes do not arrive automatically — someone must bump pins. Acceptable trade-off for a non-expert-maintained service where surprise upgrades carry more risk than delayed patches.
- This file pins direct deps only, not transitives. Full lockfile reproducibility (e.g., `pip-tools`, `uv lock`) is out of scope for this issue; can be revisited if transitive drift becomes a problem.

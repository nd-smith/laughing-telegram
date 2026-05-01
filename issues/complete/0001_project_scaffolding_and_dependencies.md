# 0001 — Project scaffolding & dependencies

## Goal

Lay down the directory structure and dependency manifest so subsequent issues have somewhere to add code.

## Scope

- Create directories per PRD §Repository Structure: `pipeline/`, `pipeline/sources/`, `shared/`, `tests/`. Each gets an empty `__init__.py`.
- Create `requirements.txt` listing the runtime dependencies from PRD §Dependencies plus `pytest` for tests:
  - `azure-eventhub`
  - `azure-identity`
  - `azure-storage-file-datalake`
  - `confluent-kafka`
  - `pyarrow`
  - `prometheus-client`
  - `pytest` (test-only)

## Out of scope

- Any code beyond empty `__init__.py` files.
- README, `setup.py`/`pyproject.toml` — not requested by the PRD.
- Linters, formatters, pre-commit hooks.
- Pre-creating empty files for future issues (no placeholders, per CLAUDE.md).

## Acceptance criteria

- All four directories exist with empty `__init__.py`.
- `requirements.txt` includes all six runtime deps plus `pytest`.
- `python -m pytest tests/` runs and exits cleanly (zero tests collected is fine).

## Notes

- **Ask before deciding** version pinning style (`==` exact, `>=` lower bound, `~=` compatible-release). Pick one and apply consistently.
- Empty `__init__.py` files are the canonical Python package marker — they are not "placeholders" in the CLAUDE.md sense.

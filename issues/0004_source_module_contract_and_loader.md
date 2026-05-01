# 0004 — Source module contract & loader

## Goal

Loader that imports a source module by name and validates it exposes the required interface. Defines the contract that all future source modules must satisfy.

## Scope

- `pipeline/sources/__init__.py` containing:
  - A module-level docstring documenting the source-module contract (the required attributes and the `extract` signature) — this is the spec future maintainers will read when adding sources.
  - A function `load_source(name: str)` that:
    - Imports `pipeline.sources.<name>` dynamically.
    - Validates the module exposes:
      - `SOURCE_NAME: str`
      - `EVENT_HUB_NAMESPACE: str`
      - `EVENT_HUB_NAME: str`
      - `KAFKA_OUTPUT_TOPIC: str`
      - `extract(raw_event: dict) -> tuple[dict, str]` (callable)
    - Raises a clear error naming the missing attribute / wrong type if the contract is unmet.
    - Returns the module on success.
- `tests/test_sources.py` covering:
  - `load_source("nonexistent")` raises with a clear message.
  - Loading a fixture source missing an attribute raises with the attribute name in the message.
  - Loading a fixture source missing `extract` or where `extract` is not callable raises clearly.
  - Loading a valid fixture source returns the module.

## Out of scope

- Any production source modules (added later as their own issues per real source).
- Caching / module reloading.

## Acceptance criteria

- `tests/test_sources.py` passes.
- The module docstring on `pipeline/sources/__init__.py` is sufficient for a maintainer to add a new source by reading only that file.

## Notes

- Test fixture sources can live under `tests/` (e.g., `tests/fixtures/sources/`) and be put on `sys.path` from `conftest.py`. **Ask** if a different layout seems cleaner.
- Don't add a registry, plugin system, or auto-discovery — the loader takes a name and imports it. That's the whole feature.

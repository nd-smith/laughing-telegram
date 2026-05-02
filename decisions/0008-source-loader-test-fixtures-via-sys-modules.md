# 0008 — Source-loader test fixtures via in-memory `sys.modules`

**Status:** Accepted
**Date:** 2026-05-02

## Context

Issue [0004](../issues/complete/0004_source_module_contract_and_loader.md) adds `pipeline/sources/__init__.py` with `load_source(name)`, which calls `importlib.import_module(f"pipeline.sources.{name}")` and then validates the imported module against the source contract (four required string constants and a callable `extract`). Tests need fixture "source modules" that are intentionally valid, intentionally missing an attribute, or intentionally have a wrong type — without polluting the production `pipeline/sources/` directory with test-only files.

The issue's Notes flagged the fixture layout as an "ask before deciding" item and suggested on-disk fixtures under `tests/fixtures/sources/` put on `sys.path` from `conftest.py`. Two options were considered:

- **On-disk fixture files.** Real `.py` files under `tests/fixtures/sources/`. To exercise the loader's actual code path, fixtures must resolve as `pipeline.sources.<name>`, which means `conftest.py` has to append the fixtures directory to `pipeline.sources.__path__` (sys.path alone resolves them as bare top-level modules instead). Adds a directory tree, a conftest path-manipulation step, and one file per fixture variant.
- **In-memory `sys.modules` fakes.** Each test constructs `types.ModuleType("pipeline.sources.<name>")`, sets or omits attributes as needed, and registers it in `sys.modules`. `importlib.import_module` returns the cached entry without touching disk, so `load_source` runs its real attribute and type checks against the fake. A `pytest` fixture tracks registered names and removes them on teardown so tests don't bleed.

The repo's guiding principle is simplicity-first for non-expert maintainers and AI-assisted troubleshooting. Each fixture file in option 1 would carry essentially the same shape with one attribute deliberately wrong; the variants read more clearly when expressed as small dict overrides next to the assertion they motivate. The on-disk path also requires a `conftest.py` that mutates a package's `__path__`, which is exactly the kind of indirection the project tries to avoid.

## Decision

Source-loader tests construct fake source modules in-memory using `types.ModuleType`, register them under `pipeline.sources.<name>` in `sys.modules`, and clean up on teardown via a `pytest` fixture. There is no `tests/fixtures/sources/` tree and no path manipulation in `conftest.py`.

## Consequences

- All test logic lives in `tests/test_sources.py` and reads top-to-bottom: the contract violation each test demonstrates is right next to the assertion that catches it.
- No `conftest.py` import-path rewiring is needed for this issue.
- The loader is exercised through its real `importlib.import_module` call — `sys.modules` caching is a documented import-system behavior, not a test-only shortcut.
- If a future test genuinely needs to exercise on-disk import (e.g. testing a syntax error in a source file, or import-time side effects), it will need a real file fixture; that's a separate, narrow case and can be added then without revisiting this decision.
- The teardown fixture is the only piece of bookkeeping — forgetting it in a new test would leave stale entries in `sys.modules` that could affect later tests in the same process.

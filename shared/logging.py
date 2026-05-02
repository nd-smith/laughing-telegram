"""Structured JSON logging for PropGateway per PRD §Observability §Structured Logging.

`setup_logging(source, level)` configures the root logger to emit one JSON
object per line to stdout, with `source` baked into every record. Per-event
context (`correlation_id`, `envelope_id`) is propagated via `contextvars`
and applied with the `log_context(...)` context manager — see ADR 0009.

Inside a `log_context(...)` block, every `logging` call from any module
automatically carries the IDs in its JSON output. Outside, the IDs are
emitted as `null` so the JSON line shape is stable.
"""

from __future__ import annotations

import contextvars
import json
import logging
import sys
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Iterator

_correlation_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "propgateway_correlation_id", default=None
)
_envelope_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "propgateway_envelope_id", default=None
)

# Stdlib LogRecord attributes that are not caller-supplied extras. Anything
# present on a record outside this set (and not starting with "_") was put
# there via `extra=` and should be merged into the JSON output.
_LOGRECORD_RESERVED_ATTRS = frozenset(
    {
        "name", "msg", "args", "levelname", "levelno", "pathname", "filename",
        "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName",
        "created", "msecs", "relativeCreated", "thread", "threadName",
        "processName", "process", "taskName", "message",
        # Stamped on by _ContextFilter — handled explicitly below.
        "correlation_id", "envelope_id",
    }
)


class _ContextFilter(logging.Filter):
    """Copies the current contextvar values onto each record."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.correlation_id = _correlation_id.get()
        record.envelope_id = _envelope_id.get()
        return True


class JsonFormatter(logging.Formatter):
    """Serialises each LogRecord to a single JSON object."""

    def __init__(self, source: str) -> None:
        super().__init__()
        self._source = source

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "source": self._source,
            "correlation_id": getattr(record, "correlation_id", None),
            "envelope_id": getattr(record, "envelope_id", None),
            "message": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key in _LOGRECORD_RESERVED_ATTRS or key.startswith("_"):
                continue
            payload[key] = value
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def setup_logging(source: str, level: str = "INFO") -> None:
    """Configure the root logger to emit JSON to stdout with `source` baked in.

    Repeated calls replace any previously installed PropGateway handler so
    that re-running setup (e.g. in tests) does not double-emit.
    """
    root = logging.getLogger()
    root.setLevel(level)
    for handler in list(root.handlers):
        root.removeHandler(handler)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter(source))
    handler.addFilter(_ContextFilter())
    root.addHandler(handler)


@contextmanager
def log_context(
    *, correlation_id: str | None = None, envelope_id: str | None = None
) -> Iterator[None]:
    """Set per-event log context for the duration of the block.

    Either argument may be ``None`` to leave that ID unset for this block.
    On exit, both contextvars are reset to their previous values via the
    tokens returned by ``ContextVar.set()``.
    """
    cid_token = _correlation_id.set(correlation_id)
    eid_token = _envelope_id.set(envelope_id)
    try:
        yield
    finally:
        _envelope_id.reset(eid_token)
        _correlation_id.reset(cid_token)

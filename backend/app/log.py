"""Structured JSON logging (one JSON object per line on stdout).

Cloud Logging parses these lines and maps `severity`; the benchmark and the dashboard read
the per-check line (`check_id`, per-agent latency, tokens, verdict). Phones, accounts, NRICs and
emails are masked in every line (security/redaction.py).
"""

from __future__ import annotations

import logging
import sys
from typing import TextIO

import structlog
from structlog.typing import EventDict, Processor, WrappedLogger

from app.security.redaction import redact_processor


def _add_severity(_logger: WrappedLogger, method_name: str, event_dict: EventDict) -> EventDict:
    event_dict["severity"] = method_name.upper()
    return event_dict


def configure_logging(level: str = "INFO", stream: TextIO | None = None) -> None:
    """JSON lines on stdout (Cloud Run). CLIs pass sys.stderr so their stdout stays clean."""
    stream = stream or sys.stdout
    shared: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        _add_severity,
    ]
    structlog.configure(
        processors=[
            *shared,
            structlog.processors.format_exc_info,
            structlog.processors.EventRenamer("message"),
            redact_processor,  # PII is masked in every log line (SECURITY_PRIVACY §2)
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.getLevelName(level.upper())),
        logger_factory=structlog.PrintLoggerFactory(file=stream),
        cache_logger_on_first_use=True,
    )

    # Route stdlib logging (uvicorn, google libs) through the same JSON renderer.
    handler = logging.StreamHandler(stream)
    handler.setFormatter(
        structlog.stdlib.ProcessorFormatter(
            foreign_pre_chain=[*shared, structlog.stdlib.add_logger_name],
            processors=[
                structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                # A stdlib traceback (uvicorn's "Exception in ASGI application") becomes a string
                # here, so redact_processor masks the exception message too.
                structlog.processors.format_exc_info,
                structlog.processors.EventRenamer("message"),
                redact_processor,
                structlog.processors.JSONRenderer(),
            ],
        )
    )
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level.upper())
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        lg = logging.getLogger(name)
        lg.handlers = []
        lg.propagate = True


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)

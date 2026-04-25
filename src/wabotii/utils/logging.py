"""Structured logging setup using structlog."""

import logging

import structlog


def setup_logging(log_level: str = "INFO", dev_mode: bool = False) -> None:
    """Configure structured logging."""
    effective_level = log_level.upper() if dev_mode else "ERROR"
    log_level_int = getattr(logging, effective_level, logging.ERROR)

    if dev_mode:
        # Development: pretty-printed output
        structlog.configure(
            processors=[
                structlog.stdlib.add_log_level,
                structlog.processors.TimeStamper(fmt="iso"),
                structlog.dev.ConsoleRenderer(),
            ],
            context_class=dict,
            logger_factory=structlog.PrintLoggerFactory(),
            wrapper_class=structlog.make_filtering_bound_logger(log_level_int),
            cache_logger_on_first_use=False,
        )
    else:
        # Production: JSON output for log aggregation
        structlog.configure(
            processors=[
                structlog.stdlib.add_log_level,
                structlog.processors.TimeStamper(fmt="iso"),
                structlog.processors.JSONRenderer(),
            ],
            context_class=dict,
            logger_factory=structlog.PrintLoggerFactory(),
            wrapper_class=structlog.make_filtering_bound_logger(log_level_int),
            cache_logger_on_first_use=False,
        )

    # Configure stdlib logging to use structlog
    logging.basicConfig(
        format="%(message)s",
        stream=None,
        level=log_level_int,
    )
    logging.getLogger("httpx").setLevel(logging.WARNING if dev_mode else logging.ERROR)
    logging.getLogger("uvicorn").setLevel(logging.WARNING if dev_mode else logging.ERROR)
    logging.getLogger("gunicorn").setLevel(logging.WARNING if dev_mode else logging.ERROR)


def get_logger(name: str = __name__) -> structlog.typing.FilteringBoundLogger:
    """Get a logger instance."""
    return structlog.get_logger(name)

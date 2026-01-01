"""
Logging configuration for the Solana Trading Bot.
Uses structlog for structured, JSON-compatible logging.
"""

import logging
import sys
from typing import Optional

import structlog


def setup_logging(debug: bool = False, log_file: Optional[str] = None) -> None:
    """
    Configure structured logging for the application.
    
    Args:
        debug: Enable debug level logging
        log_file: Optional file path for log output
    """
    # Set base log level
    log_level = logging.DEBUG if debug else logging.INFO
    
    # Configure standard library logging
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=log_level,
    )
    
    # Add file handler if specified
    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(log_level)
        logging.getLogger().addHandler(file_handler)
    
    # Configure structlog processors
    shared_processors = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.stdlib.ExtraAdder(),
    ]
    
    # Development: colored console output
    # Production: JSON output
    if debug:
        processors = shared_processors + [
            structlog.dev.ConsoleRenderer(colors=True)
        ]
    else:
        processors = shared_processors + [
            structlog.processors.JSONRenderer()
        ]
    
    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> structlog.BoundLogger:
    """
    Get a logger instance with the given name.
    
    Args:
        name: Logger name (typically module name)
        
    Returns:
        Configured structlog logger
    """
    return structlog.get_logger(name)

"""Logging configuration for the trading system."""
import logging
import logging.handlers
from pathlib import Path
from typing import Optional


def setup_logging(
    log_level: str = "INFO",
    log_file: Optional[str] = "trading_system.log",
    max_bytes: int = 10_485_760,  # 10MB
    backup_count: int = 5
):
    """
    Configure logging for the application.

    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: Path to log file (None to disable file logging)
        max_bytes: Maximum size of log file before rotation
        backup_count: Number of backup files to keep
    """
    # Create logs directory if needed
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, log_level.upper()))

    # Remove existing handlers
    root_logger.handlers.clear()

    # Create formatters
    detailed_formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s:%(funcName)s:%(lineno)d | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    simple_formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(message)s",
        datefmt="%H:%M:%S"
    )

    # Console handler (simple format)
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(simple_formatter)
    console_handler.setLevel(logging.INFO)
    root_logger.addHandler(console_handler)

    # File handler with rotation (detailed format)
    if log_file:
        file_handler = logging.handlers.RotatingFileHandler(
            log_file,
            maxBytes=max_bytes,
            backupCount=backup_count
        )
        file_handler.setFormatter(detailed_formatter)
        file_handler.setLevel(logging.DEBUG)
        root_logger.addHandler(file_handler)

    # Configure specific loggers
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)

    # Log startup message
    root_logger.info("="*60)
    root_logger.info("Trading System Starting")
    root_logger.info(f"Log level: {log_level}")
    if log_file:
        root_logger.info(f"Log file: {log_file}")
    root_logger.info("="*60)
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from rich.logging import RichHandler

from photomise.utilities.constants import LOG_DIR


def get_log_dir() -> Path:
    """Get the log directory path"""
    log_dir = LOG_DIR
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir


def setup_logging(console_level: int | None = None):
    """Setup global logging configuration using RichHandler for console output

    Args:
        console_level: optional logging level (e.g., logging.INFO). If None,
            defaults to INFO for console output.
    """
    # Create logs directory
    log_dir = get_log_dir()

    # Global app log
    app_log = log_dir / "photomise.log"

    # Configure root logger
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)

    # Remove existing handlers
    logger.handlers.clear()

    # Rotating file handler (10MB max, keep 5 backup files)
    file_handler = RotatingFileHandler(
        app_log, maxBytes=10 * 1024 * 1024, backupCount=5  # 10MB
    )
    file_handler.setLevel(logging.DEBUG)
    file_formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    file_handler.setFormatter(file_formatter)

    # Rich console handler for nicer console output (colors and markup)
    rich_handler = RichHandler(rich_tracebacks=True, markup=True)
    # Default console level to INFO if not provided
    rich_handler.setLevel(console_level if console_level is not None else logging.INFO)

    logger.addHandler(file_handler)
    logger.addHandler(rich_handler)

    return logger


def log_link(logger: logging.Logger, url: str, display_url: bool = False, label: str = None) -> None:
    """Log a rich-formatted link using the configured logger.

    This prints a [link=...]Label[/link] message so RichHandler renders it.
    """
    try:
        text = f"[link={url}]{label}[/link]" if label else f"[link={url}]{url}[/link]"
        if display_url and label:
            text += f" ({url})"
        logger.info(text)
    except Exception:
        # Fallback to plain URL if markup fails
        logger.info(f"{label}: {url}")

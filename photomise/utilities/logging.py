import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from rich.console import Console


def setup_logging():
    """Setup global logging configuration"""
    # Create logs directory
    log_dir = Path.home() / ".photomise" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    # Global app log
    app_log = log_dir / "photomise.log"

    # Configure root logger
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)

    # Rotating file handler (10MB max, keep 5 backup files)
    file_handler = RotatingFileHandler(
        app_log, maxBytes=10 * 1024 * 1024, backupCount=5  # 10MB
    )
    file_handler.setLevel(logging.DEBUG)
    file_formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    file_handler.setFormatter(file_formatter)

    # Console handler for user feedback
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.WARNING)
    console_formatter = logging.Formatter("%(message)s")
    console_handler.setFormatter(console_formatter)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    return logger, Console()

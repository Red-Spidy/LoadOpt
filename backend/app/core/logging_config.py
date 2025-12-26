import logging
import sys
from pathlib import Path
from app.core.config import settings


def setup_logging():
    """Configure application logging"""

    # Create logs directory if it doesn't exist
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO if settings.ENVIRONMENT == "production" else logging.DEBUG)

    # Remove existing handlers
    root_logger.handlers = []

    # Console handler with formatting
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    console_handler.setFormatter(console_formatter)
    root_logger.addHandler(console_handler)

    # File handler for errors
    error_handler = logging.FileHandler(log_dir / "error.log")
    error_handler.setLevel(logging.ERROR)
    error_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(pathname)s:%(lineno)d - %(message)s'
    )
    error_handler.setFormatter(error_formatter)
    root_logger.addHandler(error_handler)

    # File handler for all logs (in development)
    if settings.ENVIRONMENT != "production":
        debug_handler = logging.FileHandler(log_dir / "debug.log")
        debug_handler.setLevel(logging.DEBUG)
        debug_handler.setFormatter(error_formatter)
        root_logger.addHandler(debug_handler)

    # Set specific loggers to WARNING to reduce noise
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)

    logging.info(f"Logging configured for {settings.ENVIRONMENT} environment")

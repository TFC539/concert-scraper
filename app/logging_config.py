from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path


_LOGGING_CONFIGURED = False


def setup_logging() -> Path:
    global _LOGGING_CONFIGURED
    if _LOGGING_CONFIGURED:
        return Path(os.getenv("APP_LOG_DIR", "logs")).resolve()

    log_dir = Path(os.getenv("APP_LOG_DIR", "logs"))
    log_dir.mkdir(parents=True, exist_ok=True)

    log_level_name = os.getenv("APP_LOG_LEVEL", "INFO").upper()
    level = getattr(logging, log_level_name, logging.INFO)

    max_bytes = int(os.getenv("APP_LOG_MAX_BYTES", str(5 * 1024 * 1024)))
    backup_count = int(os.getenv("APP_LOG_BACKUP_COUNT", "5"))

    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    formatter = logging.Formatter(
        fmt="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Replace existing handlers to avoid duplicate logs after reloads.
    root_logger.handlers.clear()

    console_handler = logging.StreamHandler()
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)

    app_file_handler = RotatingFileHandler(
        log_dir / "app.log",
        maxBytes=max(1024, max_bytes),
        backupCount=max(1, backup_count),
        encoding="utf-8",
    )
    app_file_handler.setLevel(level)
    app_file_handler.setFormatter(formatter)

    error_file_handler = RotatingFileHandler(
        log_dir / "error.log",
        maxBytes=max(1024, max_bytes),
        backupCount=max(1, backup_count),
        encoding="utf-8",
    )
    error_file_handler.setLevel(logging.WARNING)
    error_file_handler.setFormatter(formatter)

    root_logger.addHandler(console_handler)
    root_logger.addHandler(app_file_handler)
    root_logger.addHandler(error_file_handler)

    # Keep Uvicorn logs visible and routed into the same handlers.
    for logger_name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        uv_logger = logging.getLogger(logger_name)
        uv_logger.handlers.clear()
        uv_logger.propagate = True
        uv_logger.setLevel(level)

    _LOGGING_CONFIGURED = True
    return log_dir.resolve()
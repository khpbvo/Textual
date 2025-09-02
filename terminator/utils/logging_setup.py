"""Shared logging configuration for the Terminator IDE.

Provides a single place to configure console + rotating file logging for the app and agents.
"""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional


def _has_filehandler(logger: logging.Logger, filename: str) -> bool:
    for h in logger.handlers:
        if isinstance(h, (logging.FileHandler, RotatingFileHandler)):
            try:
                if getattr(h, "baseFilename", "").endswith(filename):
                    return True
            except Exception:
                continue
    return False


def configure_logging(
    level: int | str = logging.INFO,
    app_log: str = "terminator.log",
    agent_log: str = "terminator_agent.log",
    max_bytes: int = 1_000_000,
    backup_count: int = 3,
) -> None:
    """Configure root and key loggers with console + rotating file handlers.

    Safe to call multiple times; avoids duplicate handlers.
    """
    if isinstance(level, str):
        level = getattr(logging, level.upper(), logging.INFO)

    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    root = logging.getLogger()
    root.setLevel(level)

    # Console handler
    if not any(isinstance(h, logging.StreamHandler) for h in root.handlers):
        sh = logging.StreamHandler()
        sh.setLevel(level)
        sh.setFormatter(fmt)
        root.addHandler(sh)

    # App file handler
    if not _has_filehandler(root, app_log):
        fh = RotatingFileHandler(app_log, maxBytes=max_bytes, backupCount=backup_count)
        fh.setLevel(level)
        fh.setFormatter(fmt)
        root.addHandler(fh)

    # Agents logger (separate file)
    agents_logger = logging.getLogger("terminator_agents")
    agents_logger.setLevel(level)
    if not _has_filehandler(agents_logger, agent_log):
        afh = RotatingFileHandler(agent_log, maxBytes=max_bytes, backupCount=backup_count)
        afh.setLevel(level)
        afh.setFormatter(fmt)
        agents_logger.addHandler(afh)
    agents_logger.propagate = True

    # Quiet noisy libraries unless debugging
    for noisy in ("httpx", "httpcore", "openai", "openai._base_client"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


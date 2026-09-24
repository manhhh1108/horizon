"""Session logging helpers (file + optional GUI callback)."""
from __future__ import annotations

import logging
from pathlib import Path


def setup_session_logger(log_path: Path, name: str = "horizon") -> logging.Logger:
    """Return a logger writing to log_path (UTF-8), one file handler per name.

    Calling again with the SAME path is a no-op (no duplicate handler). Calling
    with a DIFFERENT path (e.g. a new session) closes and removes the previous
    file handler for this logger name and attaches the new one, so logs never
    fan out to stale files and handles don't leak.
    """
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    log_path = Path(log_path)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    for h in list(logger.handlers):
        if not isinstance(h, logging.FileHandler):
            continue
        if getattr(h, "_horizon_path", None) == str(log_path):
            return logger  # already configured for this exact path
        logger.removeHandler(h)  # drop a stale handler from a previous session
        h.close()
    handler = logging.FileHandler(log_path, encoding="utf-8")
    handler._horizon_path = str(log_path)  # type: ignore[attr-defined]
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(handler)
    return logger

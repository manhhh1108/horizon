"""Session logging helpers (file + optional GUI callback)."""
from __future__ import annotations

import logging
from pathlib import Path


def setup_session_logger(log_path: Path, name: str = "horizon") -> logging.Logger:
    """Return a logger that writes to log_path (UTF-8). Idempotent per name."""
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    log_path = Path(log_path)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    # Avoid stacking duplicate file handlers for the same path.
    for h in logger.handlers:
        if isinstance(h, logging.FileHandler) and getattr(h, "_horizon_path", None) == str(log_path):
            return logger
    handler = logging.FileHandler(log_path, encoding="utf-8")
    handler._horizon_path = str(log_path)  # type: ignore[attr-defined]
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(handler)
    return logger

"""Project logger — console + rotating file under logs/. No print, no stdlib
logging direct calls anywhere else in the app."""

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

_LOGS_DIR = Path(__file__).resolve().parents[1] / "logs"
_LOGS_DIR.mkdir(exist_ok=True)

logger = logging.getLogger("ai_therapist")
logger.setLevel(logging.INFO)

_formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s")

_console = logging.StreamHandler()
_console.setFormatter(_formatter)
logger.addHandler(_console)

_file = RotatingFileHandler(_LOGS_DIR / "ai_therapist.log", maxBytes=1_000_000, backupCount=3)
_file.setFormatter(_formatter)
logger.addHandler(_file)

logger.propagate = False

__all__ = ["logger"]

"""Structured logging plus the append-only JSONL audit trail.

Two channels exist:

``logs/run.log``     human readable rolling log of everything the pipeline did.
``logs/audit.jsonl`` machine readable, append-only, one JSON object per event.

The audit log is the provenance backbone: every discovery, merge, download,
licence decision and verification verdict is written there so that a third party
can reconstruct why any row in the atlas exists.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config import get_settings

_LOCK = threading.Lock()
_CONFIGURED = False
_RUN_ID = os.environ.get("UAV_RUN_ID") or uuid.uuid4().hex[:12]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def run_id() -> str:
    return _RUN_ID


def configure_logging(verbose: bool = False) -> logging.Logger:
    """Idempotently configure the root ``uav`` logger."""
    global _CONFIGURED
    settings = get_settings()
    logger = logging.getLogger("uav")
    if _CONFIGURED:
        return logger

    level = logging.DEBUG if verbose else getattr(
        logging, settings.log_level.upper(), logging.INFO
    )
    logger.setLevel(level)
    logger.propagate = False

    fmt = logging.Formatter(
        "%(asctime)s %(levelname)-7s %(name)-28s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S%z",
    )

    stream = logging.StreamHandler(sys.stdout)
    stream.setFormatter(fmt)
    logger.addHandler(stream)

    settings.paths.logs.mkdir(parents=True, exist_ok=True)
    file_handler = logging.FileHandler(
        settings.paths.logs / "run.log", encoding="utf-8"
    )
    file_handler.setFormatter(fmt)
    logger.addHandler(file_handler)

    _CONFIGURED = True
    logger.debug("logging configured run_id=%s level=%s", _RUN_ID, level)
    return logger


def get_logger(name: str) -> logging.Logger:
    configure_logging()
    return logging.getLogger(f"uav.{name}")


def audit(
    event: str,
    *,
    agent: str = "system",
    status: str = "ok",
    **payload: Any,
) -> dict[str, Any]:
    """Append one event to ``logs/audit.jsonl`` and return the written record."""
    settings = get_settings()
    record: dict[str, Any] = {
        "ts": utc_now(),
        "monotonic": round(time.monotonic(), 4),
        "run_id": _RUN_ID,
        "agent": agent,
        "event": event,
        "status": status,
    }
    for key, value in payload.items():
        if isinstance(value, Path):
            value = str(value)
        record[key] = value

    settings.paths.logs.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, ensure_ascii=False, default=str)
    with _LOCK:
        with (settings.paths.logs / "audit.jsonl").open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    return record


class AgentLogger:
    """Convenience wrapper binding an agent name to both log channels."""

    def __init__(self, agent: str) -> None:
        self.agent = agent
        self.log = get_logger(agent)

    def info(self, message: str, *args: Any) -> None:
        self.log.info(message, *args)

    def debug(self, message: str, *args: Any) -> None:
        self.log.debug(message, *args)

    def warning(self, message: str, *args: Any) -> None:
        self.log.warning(message, *args)

    def error(self, message: str, *args: Any) -> None:
        self.log.error(message, *args)

    def event(self, event: str, *, status: str = "ok", **payload: Any) -> None:
        audit(event, agent=self.agent, status=status, **payload)

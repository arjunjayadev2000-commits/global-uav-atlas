"""Small helpers shared by every stage: logging, table persistence, provenance."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from .config import TABLES

_LOG_FORMAT = "%(asctime)s  %(levelname)-7s  %(name)-22s  %(message)s"


def get_logger(name: str) -> logging.Logger:
    """Return a configured logger; idempotent so modules can call it freely."""
    logger = logging.getLogger(name)
    if not logging.getLogger().handlers:
        logging.basicConfig(level=logging.INFO, format=_LOG_FORMAT, datefmt="%H:%M:%S")
    return logger


def save_table(df: pd.DataFrame, name: str, *, index: bool = False) -> Path:
    """Write an analysis table to ``outputs/tables`` as CSV and return its path.

    Every figure and every claim in the report is backed by one of these files,
    which is what makes the analysis auditable rather than merely reproducible.
    """
    TABLES.mkdir(parents=True, exist_ok=True)
    path = TABLES / f"{name}.csv"
    df.to_csv(path, index=index)
    get_logger("dcsc.io").info("table %-38s %6d rows -> %s", name, len(df), path.name)
    return path


def load_table(name: str) -> pd.DataFrame:
    """Read back a table written by :func:`save_table`."""
    return pd.read_csv(TABLES / f"{name}.csv")


def write_json(payload: Any, path: Path) -> Path:
    """Write ``payload`` as pretty JSON, creating parents as needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    return path


def utc_stamp() -> str:
    """Timestamp used in run manifests and on report footers."""
    return datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")


def describe_frame(df: pd.DataFrame, name: str) -> dict[str, Any]:
    """Compact profile of a frame, collected into the run manifest."""
    return {
        "name": name,
        "rows": len(df),
        "columns": list(df.columns),
        "null_counts": {c: int(df[c].isna().sum()) for c in df.columns},
        "memory_mb": round(df.memory_usage(deep=True).sum() / 1e6, 2),
    }

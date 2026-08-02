"""Central configuration for the Global UAV Visual Atlas pipeline.

All tunables are environment driven so that the same code runs identically in a
container, in CI and on a developer workstation.  Nothing here reads secrets
from disk; secrets arrive purely through the environment (see ``.env.example``).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent


def _load_dotenv(path: Path) -> None:
    """Minimal .env loader.

    We deliberately avoid a hard dependency on python-dotenv so the pipeline can
    bootstrap in a bare container.  Real environment variables always win.
    """
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


_load_dotenv(REPO_ROOT / ".env")


def _env_str(name: str, default: str) -> str:
    value = os.environ.get(name)
    return value if value not in (None, "") else default


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, "") or default)
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, "") or default)
    except ValueError:
        return default


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Paths:
    root: Path = REPO_ROOT
    data: Path = REPO_ROOT / "data"
    seed: Path = REPO_ROOT / "data" / "seed"
    imports: Path = REPO_ROOT / "data" / "imports"
    cache: Path = REPO_ROOT / "data" / "cache"
    images: Path = REPO_ROOT / "images"
    output: Path = REPO_ROOT / "output"
    logs: Path = REPO_ROOT / "logs"
    docs: Path = REPO_ROOT / "docs"

    def ensure(self) -> None:
        for value in (
            self.data,
            self.seed,
            self.imports,
            self.cache,
            self.images,
            self.output,
            self.logs,
            self.docs,
        ):
            value.mkdir(parents=True, exist_ok=True)


@dataclass(frozen=True)
class Settings:
    """Runtime settings for every agent in the pipeline."""

    paths: Paths = field(default_factory=Paths)

    # --- database -------------------------------------------------------
    database_path: Path = field(
        default_factory=lambda: Path(
            _env_str("UAV_DB_PATH", str(REPO_ROOT / "data" / "uav_atlas.sqlite"))
        )
    )

    # --- networking -----------------------------------------------------
    user_agent: str = field(
        default_factory=lambda: _env_str(
            "UAV_USER_AGENT",
            "GlobalUAVVisualAtlas/1.0 (research dataset compilation; "
            "contact via repository issues)",
        )
    )
    request_timeout: float = field(
        default_factory=lambda: _env_float("UAV_REQUEST_TIMEOUT", 30.0)
    )
    max_retries: int = field(default_factory=lambda: _env_int("UAV_MAX_RETRIES", 4))
    backoff_base: float = field(
        default_factory=lambda: _env_float("UAV_BACKOFF_BASE", 2.0)
    )
    rate_limit_per_host: float = field(
        default_factory=lambda: _env_float("UAV_RATE_LIMIT_RPS", 1.0)
    )
    respect_robots: bool = field(
        default_factory=lambda: _env_bool("UAV_RESPECT_ROBOTS", True)
    )
    http_cache_enabled: bool = field(
        default_factory=lambda: _env_bool("UAV_HTTP_CACHE", True)
    )
    http_cache_ttl_seconds: int = field(
        default_factory=lambda: _env_int("UAV_HTTP_CACHE_TTL", 7 * 24 * 3600)
    )
    offline: bool = field(default_factory=lambda: _env_bool("UAV_OFFLINE", False))

    # --- images ---------------------------------------------------------
    image_min_width: int = field(
        default_factory=lambda: _env_int("UAV_IMAGE_MIN_WIDTH", 500)
    )
    image_preferred_width: int = field(
        default_factory=lambda: _env_int("UAV_IMAGE_PREFERRED_WIDTH", 800)
    )
    image_max_bytes: int = field(
        default_factory=lambda: _env_int("UAV_IMAGE_MAX_BYTES", 25 * 1024 * 1024)
    )
    thumbnail_width: int = field(
        default_factory=lambda: _env_int("UAV_THUMBNAIL_WIDTH", 320)
    )
    atlas_image_width: int = field(
        default_factory=lambda: _env_int("UAV_ATLAS_IMAGE_WIDTH", 640)
    )
    generate_webp: bool = field(
        default_factory=lambda: _env_bool("UAV_GENERATE_WEBP", True)
    )
    allow_noncommercial_licenses: bool = field(
        default_factory=lambda: _env_bool("UAV_ALLOW_NC_LICENSES", False)
    )

    # --- vision verification -------------------------------------------
    anthropic_api_key: str = field(
        default_factory=lambda: _env_str("ANTHROPIC_API_KEY", "")
    )
    vision_model: str = field(
        default_factory=lambda: _env_str("UAV_VISION_MODEL", "claude-sonnet-5")
    )
    vision_enabled: bool = field(
        default_factory=lambda: _env_bool("UAV_VISION_ENABLED", True)
    )
    vision_max_calls: int = field(
        default_factory=lambda: _env_int("UAV_VISION_MAX_CALLS", 0)  # 0 == unlimited
    )

    # --- deduplication --------------------------------------------------
    dedupe_auto_merge_threshold: float = field(
        default_factory=lambda: _env_float("UAV_DEDUPE_AUTO", 0.94)
    )
    dedupe_review_threshold: float = field(
        default_factory=lambda: _env_float("UAV_DEDUPE_REVIEW", 0.86)
    )

    # --- discovery ------------------------------------------------------
    discovery_stop_after_empty_passes: int = field(
        default_factory=lambda: _env_int("UAV_DISCOVERY_EMPTY_PASSES", 3)
    )
    discovery_max_passes: int = field(
        default_factory=lambda: _env_int("UAV_DISCOVERY_MAX_PASSES", 12)
    )

    # --- logging --------------------------------------------------------
    log_level: str = field(default_factory=lambda: _env_str("UAV_LOG_LEVEL", "INFO"))

    def as_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for key, value in self.__dict__.items():
            if key == "paths":
                continue
            if key == "anthropic_api_key":
                out[key] = "***set***" if value else ""
                continue
            out[key] = str(value) if isinstance(value, Path) else value
        return out


SETTINGS = Settings()
SETTINGS.paths.ensure()


def get_settings() -> Settings:
    return SETTINGS

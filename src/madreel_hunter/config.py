"""Configuration loading.

Lookup order for every value (first hit wins):

1. ``--config`` path given on the command line
2. ``./config.toml``
3. ``~/.config/madreel-hunter/config.toml``
4. environment variables (``MADREEL_API_KEY`` / ``MADREEL_BASE_URL`` / ``TMDB_API_KEY``)

An API key is never written to logs or to the output of ``mh doctor``; only its
first 8 characters (the ``kid``) are ever printed.
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

DEFAULT_BASE_URL = "https://madow.tv"
DEFAULT_CONFIG_PATHS = (
    Path("config.toml"),
    Path.home() / ".config" / "madreel-hunter" / "config.toml",
)


class ConfigError(RuntimeError):
    """Raised when configuration is missing or invalid."""


@dataclass(slots=True)
class Config:
    api_key: str = ""
    base_url: str = DEFAULT_BASE_URL
    tmdb_api_key: str = ""
    template: str = ""
    proxy: str = ""
    timeout: float = 20.0
    scoring: dict[str, Any] = field(default_factory=dict)
    targets: dict[str, Any] = field(default_factory=dict)
    source_path: Path | None = None

    @property
    def kid(self) -> str:
        return self.api_key[:8] if self.api_key else ""

    def require_api_key(self) -> str:
        if not self.api_key:
            raise ConfigError(
                "No OpenAPI key configured. Create one at "
                "https://madow.tv (账户 → API Key) and set MADREEL_API_KEY "
                "or api_key in config.toml."
            )
        return self.api_key


def load_config(path: str | Path | None = None) -> Config:
    """Load configuration from disk, then fall back to environment variables."""
    data: dict[str, Any] = {}
    source: Path | None = None

    candidates = [Path(path)] if path else list(DEFAULT_CONFIG_PATHS)
    for candidate in candidates:
        if candidate and candidate.is_file():
            try:
                data = tomllib.loads(candidate.read_text(encoding="utf-8"))
            except tomllib.TOMLDecodeError as exc:  # pragma: no cover - user input
                raise ConfigError(f"Invalid TOML in {candidate}: {exc}") from exc
            source = candidate
            break

    api = data.get("api", {})
    config = Config(
        api_key=str(api.get("key") or ""),
        base_url=str(api.get("base_url") or DEFAULT_BASE_URL).rstrip("/"),
        tmdb_api_key=str(data.get("tmdb", {}).get("api_key") or ""),
        template=str(data.get("share", {}).get("template") or ""),
        proxy=str(data.get("http", {}).get("proxy") or ""),
        timeout=float(data.get("http", {}).get("timeout") or 20.0),
        scoring=data.get("scoring", {}) or {},
        targets=data.get("targets", {}) or {},
        source_path=source,
    )

    config.api_key = os.environ.get("MADREEL_API_KEY", config.api_key)
    config.base_url = os.environ.get("MADREEL_BASE_URL", config.base_url).rstrip("/")
    config.tmdb_api_key = os.environ.get("TMDB_API_KEY", config.tmdb_api_key)
    return config

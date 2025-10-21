"""Configuration loading utilities for the daily review engine."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

import yaml
from dotenv import load_dotenv


@dataclass
class Config:
    """Simple wrapper that exposes dictionary-like access to loaded settings."""

    data: Dict[str, Any]

    def get(self, key: str, default: Any = None) -> Any:
        return self.data.get(key, default)

    def __getitem__(self, item: str) -> Any:  # pragma: no cover - convenience proxy
        return self.data[item]


def load_config(path: Optional[Path | str] = None) -> Config:
    """Load configuration from ``config.yaml`` and optional ``.env`` file."""
    load_dotenv()
    config_path = Path(path) if path else Path("config.yaml")
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")
    with config_path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    return Config(data=data)


def require_env(var_name: str) -> str:
    """Return an environment variable or raise a descriptive error."""
    value = os.getenv(var_name)
    if not value:
        raise RuntimeError(f"Environment variable {var_name} is required but missing")
    return value


__all__ = ["Config", "load_config", "require_env"]

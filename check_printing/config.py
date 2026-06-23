from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from check_printing.models import AppConfig

DEFAULT_CONFIG_PATH = Path("config.local.yaml")


def load_config(path: Path = DEFAULT_CONFIG_PATH) -> AppConfig:
    if not path.exists():
        return AppConfig()
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a YAML mapping")
    return AppConfig.model_validate(data)


def save_config(config: AppConfig, path: Path = DEFAULT_CONFIG_PATH) -> None:
    path.write_text(
        yaml.safe_dump(_to_yamlable(config.model_dump(mode="json")), sort_keys=False),
        encoding="utf-8",
    )


def _to_yamlable(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _to_yamlable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_to_yamlable(item) for item in value]
    return value

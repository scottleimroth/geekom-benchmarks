"""Config loading: models.yaml, tasks.yaml, hardware.yaml.

Config is data, not code. Runners ask this module for the enabled model set and
for task definitions; nothing else reads the YAML directly.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from .utils.io import paths

DEFAULT_ENDPOINT = os.environ.get("LEMONADE_URL", "http://127.0.0.1:13305/api/v1")


@dataclass
class ModelSpec:
    id: str
    display_name: str
    provider: str = "lemonade"
    endpoint: str = DEFAULT_ENDPOINT
    backend: Optional[str] = None
    family: Optional[str] = None
    param_size: Optional[float] = None
    arch: Optional[str] = None  # "dense" | "moe"
    quant: Optional[str] = None
    uses: List[str] = field(default_factory=list)
    context_window: Optional[int] = None
    notes: Optional[str] = None
    enabled: bool = True
    skip_reason: Optional[str] = None
    pull_command: Optional[str] = None
    raw: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ModelSpec":
        return cls(
            id=d["id"],
            display_name=d.get("display_name", d["id"]),
            provider=d.get("provider", "lemonade"),
            endpoint=d.get("endpoint", DEFAULT_ENDPOINT),
            backend=d.get("backend"),
            family=d.get("family"),
            param_size=d.get("param_size"),
            arch=d.get("arch"),
            quant=d.get("quant"),
            uses=list(d.get("uses", [])),
            context_window=d.get("context_window"),
            notes=d.get("notes"),
            enabled=bool(d.get("enabled", True)),
            skip_reason=d.get("skip_reason"),
            pull_command=d.get("pull_command"),
            raw=d,
        )


def _config_dir() -> Path:
    return paths()["config"]


def load_models(config_path: Optional[Path] = None) -> List[ModelSpec]:
    path = config_path or (_config_dir() / "models.yaml")
    if not path.exists():
        return []
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return [ModelSpec.from_dict(m) for m in data.get("models", [])]


def load_tasks(config_path: Optional[Path] = None) -> Dict[str, Any]:
    path = config_path or (_config_dir() / "tasks.yaml")
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def load_hardware(config_path: Optional[Path] = None) -> Dict[str, Any]:
    path = config_path or (_config_dir() / "hardware.yaml")
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def select_models(
    spec: str = "all",
    *,
    uses: Optional[str] = None,
    include_disabled: bool = False,
) -> List[ModelSpec]:
    """Resolve a --models argument to a list of ModelSpec.

    `spec` is "all" or a comma-separated list of model ids / display names.
    `uses` optionally filters to a use-tag (e.g. "vision", "coding").
    Disabled models are excluded unless include_disabled=True.
    """
    models = load_models()
    if uses:
        models = [m for m in models if uses in m.uses]
    if spec and spec != "all":
        wanted = {s.strip().lower() for s in spec.split(",") if s.strip()}
        models = [
            m
            for m in models
            if m.id.lower() in wanted or m.display_name.lower() in wanted
        ]
    if not include_disabled:
        models = [m for m in models if m.enabled]
    return models

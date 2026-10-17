from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent


@dataclass
class Config:
    root: Path
    data: dict[str, Any]
    character: dict[str, Any]

    def path(self, key: str) -> Path:
        return self.root / self.data["paths"][key]

    @property
    def channel(self) -> dict[str, Any]:
        return self.data["channel"]

    @property
    def youtube(self) -> dict[str, Any]:
        return self.data["youtube"]

    @property
    def video(self) -> dict[str, Any]:
        return self.data["video"]


def load_config(root: Path = ROOT) -> Config:
    data = yaml.safe_load((root / "config.yaml").read_text(encoding="utf-8"))
    character = yaml.safe_load((root / "channel" / "character.yaml").read_text(encoding="utf-8"))
    return Config(root=root, data=data, character=character)

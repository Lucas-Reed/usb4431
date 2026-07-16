from __future__ import annotations

import json
import os
from pathlib import Path

from .model import AcquisitionConfig


def default_settings_path() -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA")
    base = Path(local_app_data) if local_app_data else Path.home() / "AppData" / "Local"
    return base / "USB4431Monitor" / "settings.json"


class SettingsStore:
    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path is not None else default_settings_path()

    def load(self) -> tuple[dict, str | None]:
        if not self.path.exists():
            return AcquisitionConfig().to_ui(), None
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                raise ValueError("配置文件内容不是对象")
            config = AcquisitionConfig.from_ui(raw)
            unit = raw.get("window_unit", "ms")
            return config.to_ui(unit), None
        except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
            return AcquisitionConfig().to_ui(), f"默认参数文件无效，已使用内置参数：{exc}"

    def save(self, raw: dict) -> dict:
        config = AcquisitionConfig.from_ui(raw)
        normalized = config.to_ui(raw.get("window_unit", "ms"))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(normalized, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary.replace(self.path)
        return normalized


"""Configuration loading and saving — YAML-based settings in ~/.config/fileconverter/."""

from __future__ import annotations
import os
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from fileconverter.presets import ConversionPreset

CONFIG_DIR = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "fileconverter"
CONFIG_FILE = CONFIG_DIR / "settings.yaml"

# PyInstaller bundles data files into sys._MEIPASS; source installs use relative path
_BASE_DIR = Path(getattr(sys, '_MEIPASS', Path(__file__).parent.parent))
DEFAULT_PRESETS_FILE = _BASE_DIR / "resources" / "default_presets.yaml"


HWACCEL_MODES = ["off", "auto", "nvenc", "vaapi"]


@dataclass
class Settings:
    max_simultaneous_conversions: int = 2
    exit_when_done: bool = True
    exit_delay_seconds: int = 3
    hardware_acceleration: str = "off"  # off | auto | nvenc | vaapi
    language: str = "auto"  # auto (system) | locale code like "it_IT"
    presets: list[ConversionPreset] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "version": 1,
            "max_simultaneous_conversions": self.max_simultaneous_conversions,
            "exit_when_done": self.exit_when_done,
            "exit_delay_seconds": self.exit_delay_seconds,
            "hardware_acceleration": self.hardware_acceleration,
            "language": self.language,
            "presets": [p.to_dict() for p in self.presets],
        }

    @classmethod
    def from_dict(cls, data: dict) -> Settings:
        hw = data.get("hardware_acceleration", "off")
        if hw not in HWACCEL_MODES:
            hw = "off"
        return cls(
            max_simultaneous_conversions=data.get("max_simultaneous_conversions", 2),
            exit_when_done=data.get("exit_when_done", True),
            exit_delay_seconds=data.get("exit_delay_seconds", 3),
            hardware_acceleration=hw,
            language=data.get("language", "auto"),
            presets=[ConversionPreset.from_dict(p) for p in data.get("presets", [])],
        )


def ensure_config() -> None:
    """Create config directory and copy default presets if settings.yaml doesn't exist."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    if not CONFIG_FILE.exists() and DEFAULT_PRESETS_FILE.exists():
        shutil.copy2(DEFAULT_PRESETS_FILE, CONFIG_FILE)


def load_settings() -> Settings:
    """Load settings from YAML config, falling back to defaults."""
    ensure_config()
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE, "r") as f:
            data = yaml.safe_load(f) or {}
        return Settings.from_dict(data)

    if DEFAULT_PRESETS_FILE.exists():
        with open(DEFAULT_PRESETS_FILE, "r") as f:
            data = yaml.safe_load(f) or {}
        return Settings.from_dict(data)

    return Settings()


def save_settings(settings: Settings) -> None:
    """Save settings to YAML config file."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, "w") as f:
        yaml.dump(settings.to_dict(), f, default_flow_style=False, sort_keys=False, allow_unicode=True)

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


CURRENT_VERSION = 2


@dataclass
class Settings:
    max_simultaneous_conversions: int = 2
    exit_when_done: bool = True
    exit_delay_seconds: int = 3
    hardware_acceleration: str = "off"  # off | auto | nvenc | vaapi
    language: str = "auto"  # auto (system) | locale code like "it_IT"
    presets: list[ConversionPreset] = field(default_factory=list)
    version: int = CURRENT_VERSION

    def to_dict(self) -> dict:
        return {
            "version": self.version,
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
            version=data.get("version", 1),
        )


def ensure_config() -> None:
    """Create config directory and copy default presets if settings.yaml doesn't exist."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    if not CONFIG_FILE.exists() and DEFAULT_PRESETS_FILE.exists():
        shutil.copy2(DEFAULT_PRESETS_FILE, CONFIG_FILE)


def _load_default_settings() -> Settings | None:
    if not DEFAULT_PRESETS_FILE.exists():
        return None
    with open(DEFAULT_PRESETS_FILE, "r") as f:
        data = yaml.safe_load(f) or {}
    return Settings.from_dict(data)


def load_settings() -> Settings:
    """Load settings from YAML config, falling back to defaults.

    Every load runs an additive merge: any default preset whose name is
    missing from the user config is appended.

    When the user config version is older than the bundled default version,
    we also union the input_types of presets that exist in both — so a user
    who hasn't customised inputs picks up newly supported formats. User
    settings (quality, scale, etc.) are never touched.
    """
    ensure_config()
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE, "r") as f:
            data = yaml.safe_load(f) or {}
        settings = Settings.from_dict(data)

        defaults = _load_default_settings()
        if defaults is not None:
            changed = False
            existing = {p.name: p for p in settings.presets}
            new_names = [p.name for p in defaults.presets if p.name not in existing]

            for d in defaults.presets:
                if d.name not in existing:
                    settings.presets.append(d)
                    changed = True
                elif settings.version < CURRENT_VERSION:
                    # Union input_types so older configs gain newly supported inputs.
                    user_p = existing[d.name]
                    merged = sorted(set(user_p.input_types) | set(d.input_types))
                    if merged != user_p.input_types:
                        user_p.input_types = merged
                        changed = True

            if settings.version < CURRENT_VERSION:
                settings.version = CURRENT_VERSION
                changed = True

            if changed:
                save_settings(settings)
        return settings

    defaults = _load_default_settings()
    if defaults is not None:
        return defaults

    return Settings()


def save_settings(settings: Settings) -> None:
    """Save settings to YAML config file."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, "w") as f:
        yaml.dump(settings.to_dict(), f, default_flow_style=False, sort_keys=False, allow_unicode=True)

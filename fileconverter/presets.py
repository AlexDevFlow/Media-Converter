"""Conversion preset model — ported from ConversionPreset.cs."""

from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class ConversionPreset:
    name: str
    output_type: str
    input_types: list[str] = field(default_factory=list)
    input_post_action: str = "none"  # none | archive | delete
    output_template: str = "(p)(f)"
    settings: dict = field(default_factory=dict)

    @property
    def folder_path(self) -> list[str]:
        """Return folder hierarchy from preset name (e.g. 'Video/To Mp4' -> ['Video'])."""
        parts = self.name.split("/")
        return parts[:-1]

    @property
    def short_name(self) -> str:
        """Return the leaf name (e.g. 'Video/To Mp4' -> 'To Mp4')."""
        return self.name.split("/")[-1]

    def get_setting(self, key: str, default=None):
        return self.settings.get(key, default)

    def get_setting_bool(self, key: str, default: bool = False) -> bool:
        val = self.settings.get(key, default)
        if isinstance(val, bool):
            return val
        if isinstance(val, str):
            return val.lower() in ("true", "1", "yes")
        return bool(val)

    def get_setting_int(self, key: str, default: int = 0) -> int:
        return int(self.settings.get(key, default))

    def get_setting_float(self, key: str, default: float = 0.0) -> float:
        return float(self.settings.get(key, default))

    def accepts_extension(self, ext: str) -> bool:
        return ext.lower().lstrip(".") in self.input_types

    def accepts_all_extensions(self, extensions: list[str]) -> bool:
        return all(self.accepts_extension(e) for e in extensions)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "output_type": self.output_type,
            "input_types": self.input_types,
            "input_post_action": self.input_post_action,
            "output_template": self.output_template,
            "settings": self.settings,
        }

    @classmethod
    def from_dict(cls, data: dict) -> ConversionPreset:
        return cls(
            name=data["name"],
            output_type=data["output_type"],
            input_types=data.get("input_types", []),
            input_post_action=data.get("input_post_action", "none"),
            output_template=data.get("output_template", "(p)(f)"),
            settings=data.get("settings", {}),
        )

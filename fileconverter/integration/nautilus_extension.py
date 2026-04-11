"""Nautilus-python extension — provides dynamic context menu with preset subfolders.

This file is installed to ~/.local/share/nautilus-python/extensions/ and loaded
by Nautilus at startup. It reads presets from the fileconverter config and builds
a hierarchical "File Converter" context menu filtered by selected file types.

Ported from FileConverterExtension.cs.
"""

from __future__ import annotations
import os
import shutil
import subprocess
import sys
import logging
from pathlib import Path

log = logging.getLogger("fileconverter-nautilus")

# nautilus-python provides the gi bindings
try:
    from gi.repository import Nautilus, GObject
except ImportError:
    # If Nautilus GIR is not available, this module is being imported outside Nautilus
    pass

# Config paths
_CONFIG_DIR = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "fileconverter"
_CONFIG_FILE = _CONFIG_DIR / "settings.yaml"

# These are written by the installer to help find the binary
_PROJECT_ROOT_FILE = _CONFIG_DIR / ".project_root"
_BINARY_PATH_FILE = _CONFIG_DIR / ".binary_path"


def _load_presets():
    """Load presets from the YAML config file."""
    try:
        import yaml
        if _CONFIG_FILE.exists():
            with open(_CONFIG_FILE, "r") as f:
                data = yaml.safe_load(f) or {}
            return data.get("presets", [])
    except Exception as e:
        log.error(f"Failed to load presets: {e}")
    return []


def _preset_accepts_all(preset_data, extensions):
    """Check if a preset supports all the given extensions."""
    input_types = set(preset_data.get("input_types", []))
    return all(ext in input_types for ext in extensions)


def _get_project_root() -> str:
    """Read the saved project root path."""
    if _PROJECT_ROOT_FILE.exists():
        return _PROJECT_ROOT_FILE.read_text().strip()
    return ""


def _find_fileconverter():
    """Find the fileconverter executable."""
    import shutil

    # First check the saved binary path (written by --install)
    if _BINARY_PATH_FILE.exists():
        saved = _BINARY_PATH_FILE.read_text().strip()
        if saved and os.path.isfile(saved) and os.access(saved, os.X_OK):
            return saved

    for path in [
        os.path.expanduser("~/.local/bin/fileconverter"),
        "/usr/local/bin/fileconverter",
        "/usr/bin/fileconverter",
    ]:
        if os.path.isfile(path) and os.access(path, os.X_OK):
            return path
    found = shutil.which("fileconverter")
    if found:
        return found
    return None


def _build_cmd(args: list[str]) -> list[str]:
    """Build the command to run fileconverter, handling PATH and PYTHONPATH issues."""
    fc = _find_fileconverter()
    if fc:
        return [fc] + args

    # Fallback: run python3 -m fileconverter with the correct PYTHONPATH
    python = shutil.which("python3") or "/usr/bin/python3"
    return [python, "-m", "fileconverter"] + args


def _get_env() -> dict:
    """Get environment with PYTHONPATH set to include the project root."""
    env = os.environ.copy()
    project_root = _get_project_root()
    if project_root:
        existing = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = f"{project_root}:{existing}" if existing else project_root
    return env


def _launch_conversion(preset_name, file_paths):
    """Launch fileconverter with the given preset and files."""
    cmd = _build_cmd(["--conversion-preset", preset_name] + file_paths)
    log.info(f"Launching: {' '.join(cmd)}")
    try:
        subprocess.Popen(cmd, start_new_session=True, env=_get_env())
    except Exception as e:
        log.error(f"Failed to launch fileconverter: {e}")


def _launch_settings():
    """Open the settings window."""
    cmd = _build_cmd(["--settings"])
    log.info(f"Launching settings: {' '.join(cmd)}")
    try:
        subprocess.Popen(cmd, start_new_session=True, env=_get_env())
    except Exception as e:
        log.error(f"Failed to launch settings: {e}")


class FileConverterMenuProvider(GObject.GObject, Nautilus.MenuProvider):
    """Nautilus context menu extension for File Converter."""

    def get_file_items(self, *args):
        """Build the context menu when files are selected."""
        # Handle both Nautilus 4.0 API (single arg) and 3.0 API (window, files)
        if len(args) == 1:
            files = args[0]
        elif len(args) >= 2:
            files = args[1]
        else:
            return []

        if not files:
            return []

        # Get file paths and extensions
        file_paths = []
        extensions = set()
        for f in files:
            uri = f.get_uri()
            if uri.startswith("file://"):
                path = uri[7:]
                # Handle URL encoding
                try:
                    from urllib.parse import unquote
                    path = unquote(path)
                except ImportError:
                    pass
                file_paths.append(path)
                _, ext = os.path.splitext(path)
                if ext:
                    extensions.add(ext.lower().lstrip("."))

        if not file_paths or not extensions:
            return []

        # Load presets and filter by compatibility
        presets = _load_presets()
        compatible = [p for p in presets if _preset_accepts_all(p, extensions)]

        if not compatible:
            return []

        # Build menu hierarchy
        top_item = Nautilus.MenuItem(
            name="FileConverter::TopMenu",
            label="File Converter",
            tip="Convert files using File Converter",
        )
        submenu = Nautilus.Menu()
        top_item.set_submenu(submenu)

        # Group presets by folder path
        folders: dict[str, Nautilus.Menu] = {}
        counter = 0

        for preset_data in compatible:
            name = preset_data.get("name", "")
            parts = name.split("/")
            short_name = parts[-1]
            folder_parts = parts[:-1]

            # Determine parent menu
            parent_menu = submenu
            if folder_parts:
                folder_key = "/".join(folder_parts)
                if folder_key not in folders:
                    # Create folder menu item
                    folder_item = Nautilus.MenuItem(
                        name=f"FileConverter::Folder_{counter}",
                        label=folder_parts[-1],
                        tip=f"Folder: {folder_key}",
                    )
                    counter += 1
                    folder_menu = Nautilus.Menu()
                    folder_item.set_submenu(folder_menu)
                    submenu.append_item(folder_item)
                    folders[folder_key] = folder_menu
                parent_menu = folders[folder_key]

            # Create preset menu item
            item = Nautilus.MenuItem(
                name=f"FileConverter::Preset_{counter}",
                label=short_name,
                tip=f"Convert to {preset_data.get('output_type', '').upper()}",
            )
            counter += 1
            item.connect("activate", self._on_preset_activate, name, file_paths)
            parent_menu.append_item(item)

        # Add separator and settings option
        sep = Nautilus.MenuItem(
            name="FileConverter::Sep",
            label="─────────────",
            tip="",
        )
        sep.set_property("sensitive", False)
        submenu.append_item(sep)

        settings_item = Nautilus.MenuItem(
            name="FileConverter::Settings",
            label="Configure presets...",
            tip="Open File Converter settings",
        )
        settings_item.connect("activate", self._on_settings_activate)
        submenu.append_item(settings_item)

        return [top_item]

    def _on_preset_activate(self, _item, preset_name, file_paths):
        _launch_conversion(preset_name, file_paths)

    def _on_settings_activate(self, _item):
        _launch_settings()

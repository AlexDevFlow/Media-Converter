"""Preset picker dialog — fallback for file managers without submenu support.

Shows a filtered list of compatible presets for the selected files.
Usage: fileconverter-pick file1.avi file2.mkv
"""

from __future__ import annotations
import os
import subprocess
import shutil
import sys

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw

from fileconverter import i18n
from fileconverter.i18n import _


def _find_fileconverter():
    for path in [
        os.path.expanduser("~/.local/bin/fileconverter"),
        "/usr/local/bin/fileconverter",
        "/usr/bin/fileconverter",
    ]:
        if os.path.isfile(path) and os.access(path, os.X_OK):
            return path
    found = shutil.which("fileconverter")
    return found


class PresetPickerWindow(Gtk.ApplicationWindow):
    def __init__(self, app, file_paths: list[str], presets: list[dict]):
        super().__init__(application=app, title=_("File Converter — Select Preset"),
                         default_width=400, default_height=500)
        self.file_paths = file_paths
        self.presets = presets

        header = Gtk.HeaderBar()
        self.set_titlebar(header)

        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)

        # Info label
        n = len(file_paths)
        if n == 1:
            info_text = _("{count} file selected").format(count=n)
        else:
            info_text = _("{count} files selected").format(count=n)
        info = Gtk.Label(
            label=info_text,
            margin_start=12, margin_end=12, margin_top=12, margin_bottom=8,
        )
        info.add_css_class("dim-label")
        main_box.append(info)

        # Preset list
        scroll = Gtk.ScrolledWindow(vexpand=True, hexpand=True)
        self.listbox = Gtk.ListBox()
        self.listbox.set_selection_mode(Gtk.SelectionMode.NONE)
        scroll.set_child(self.listbox)
        main_box.append(scroll)

        # Group by folders
        current_folder = None
        for preset_data in presets:
            name = preset_data.get("name", "")
            parts = name.split("/")
            folder = "/".join(parts[:-1]) if len(parts) > 1 else ""
            short_name = parts[-1]

            if folder and folder != current_folder:
                current_folder = folder
                sep_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
                sep_row.set_margin_start(12)
                sep_row.set_margin_top(8)
                sep_row.set_margin_bottom(4)
                folder_label = Gtk.Label(label=folder, xalign=0)
                folder_label.add_css_class("heading")
                sep_row.append(folder_label)
                self.listbox.append(sep_row)

            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            row.set_margin_start(12)
            row.set_margin_end(12)
            row.set_margin_top(4)
            row.set_margin_bottom(4)

            label = Gtk.Label(label=short_name, xalign=0, hexpand=True)
            row.append(label)

            out_label = Gtk.Label(label=preset_data.get("output_type", "").upper())
            out_label.add_css_class("dim-label")
            row.append(out_label)

            btn = Gtk.Button(label=_("Convert"))
            btn.add_css_class("suggested-action")
            btn.connect("clicked", self._on_convert, name)
            row.append(btn)

            self.listbox.append(row)

        self.set_child(main_box)

    def _on_convert(self, _btn, preset_name: str):
        fc = _find_fileconverter()
        if fc:
            cmd = [fc, "--conversion-preset", preset_name] + self.file_paths
        else:
            cmd = [sys.executable, "-m", "fileconverter", "--conversion-preset", preset_name] + self.file_paths
        subprocess.Popen(cmd, start_new_session=True)
        self.get_application().quit()


class PickerApp(Adw.Application):
    def __init__(self, file_paths: list[str]):
        super().__init__(application_id="org.fileconverter.picker")
        self.file_paths = [os.path.abspath(f) for f in file_paths]
        self.connect("activate", self._on_activate)

    def _on_activate(self, _app):
        from fileconverter.config import load_settings
        settings = load_settings()
        i18n.init(settings.language)

        extensions = set()
        for f in self.file_paths:
            ext = os.path.splitext(f)[1]
            if ext:
                extensions.add(ext.lower().lstrip("."))
        compatible = []
        for p in settings.presets:
            if all(ext in p.input_types for ext in extensions):
                compatible.append(p.to_dict())

        if not compatible:
            dialog = Gtk.AlertDialog()
            dialog.set_message(_("No compatible presets"))
            dialog.set_detail(_("No presets support all selected file types: {types}").format(
                types=", ".join(sorted(extensions))))
            dialog.show(None)
            return

        win = PresetPickerWindow(self, self.file_paths, compatible)
        win.present()


def main():
    import sys as _sys
    files = _sys.argv[1:]
    if not files:
        print("Usage: fileconverter-pick file1 file2 ...", file=_sys.stderr)
        _sys.exit(1)
    app = PickerApp(files)
    app.run(None)


if __name__ == "__main__":
    main()

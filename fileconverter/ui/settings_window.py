"""GTK 4 settings window — preset editor."""

from __future__ import annotations
import os

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, GLib

from fileconverter.config import load_settings, save_settings, Settings, HWACCEL_MODES
from fileconverter.helpers import ALL_INPUT_EXTENSIONS, OUTPUT_TYPES
from fileconverter.presets import ConversionPreset


class PresetEditor(Gtk.Box):
    """Editor panel for a single preset."""

    def __init__(self, preset: ConversionPreset, on_change):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.preset = preset
        self._on_change = on_change
        self.set_margin_start(12)
        self.set_margin_end(12)
        self.set_margin_top(12)
        self.set_margin_bottom(12)

        # Name
        name_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        name_box.append(Gtk.Label(label="Name:", xalign=0))
        self.name_entry = Gtk.Entry(text=preset.name, hexpand=True)
        self.name_entry.connect("changed", self._on_name_changed)
        name_box.append(self.name_entry)
        self.append(name_box)

        # Output type
        out_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        out_box.append(Gtk.Label(label="Output:", xalign=0))
        self.output_combo = Gtk.DropDown.new_from_strings(OUTPUT_TYPES)
        if preset.output_type in OUTPUT_TYPES:
            self.output_combo.set_selected(OUTPUT_TYPES.index(preset.output_type))
        self.output_combo.connect("notify::selected", self._on_output_changed)
        out_box.append(self.output_combo)
        self.append(out_box)

        # Input types
        self.append(Gtk.Label(label="Input types:", xalign=0))
        input_scroll = Gtk.ScrolledWindow(vexpand=True, min_content_height=150)
        input_flow = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, max_children_per_line=8)
        self._input_checks = {}
        for ext in ALL_INPUT_EXTENSIONS:
            check = Gtk.CheckButton(label=ext, active=ext in preset.input_types)
            check.connect("toggled", self._on_input_toggled, ext)
            input_flow.append(check)
            self._input_checks[ext] = check
        input_scroll.set_child(input_flow)
        self.append(input_scroll)

        # Settings section
        self.append(Gtk.Separator())
        self.append(Gtk.Label(label="Conversion settings:", xalign=0))

        settings_grid = Gtk.Grid(column_spacing=12, row_spacing=6)
        row = 0

        # Common settings
        common_settings = [
            ("video_quality", "Video Quality (0-63)", 0, 63, 28),
            ("video_encoding_speed", "Encoding Speed", None, None, None),
            ("video_scale", "Video Scale", 0.1, 4.0, 1.0),
            ("video_rotation", "Rotation (degrees)", 0, 270, 0),
            ("audio_bitrate", "Audio Bitrate", 16, 500, 155),
            ("image_quality", "Image Quality (0-100)", 0, 100, 85),
            ("image_scale", "Image Scale", 0.1, 4.0, 1.0),
            ("enable_audio", "Enable Audio", None, None, True),
        ]

        for key, label, min_val, max_val, default in common_settings:
            settings_grid.attach(Gtk.Label(label=label, xalign=0), 0, row, 1, 1)
            current = preset.settings.get(key, default)

            if isinstance(default, bool) or key == "enable_audio":
                check = Gtk.CheckButton(active=bool(current) if current is not None else True)
                check.connect("toggled", self._on_setting_bool, key)
                settings_grid.attach(check, 1, row, 1, 1)
            elif key == "video_encoding_speed":
                speeds = ["ultrafast", "superfast", "veryfast", "faster", "fast",
                          "medium", "slow", "slower", "veryslow"]
                combo = Gtk.DropDown.new_from_strings(speeds)
                curr_speed = str(current or "medium").lower()
                if curr_speed in speeds:
                    combo.set_selected(speeds.index(curr_speed))
                combo.connect("notify::selected", self._on_setting_combo, key, speeds)
                settings_grid.attach(combo, 1, row, 1, 1)
            else:
                val = float(current) if current is not None else float(default)
                adj = Gtk.Adjustment(value=val, lower=float(min_val), upper=float(max_val),
                                     step_increment=1, page_increment=5)
                spin = Gtk.SpinButton(adjustment=adj, digits=2 if isinstance(default, float) else 0)
                spin.connect("value-changed", self._on_setting_spin, key)
                settings_grid.attach(spin, 1, row, 1, 1)
            row += 1

        self.append(settings_grid)

        # Post-conversion action
        action_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        action_box.append(Gtk.Label(label="After conversion:", xalign=0))
        actions = ["none", "archive", "delete"]
        action_combo = Gtk.DropDown.new_from_strings(actions)
        if preset.input_post_action in actions:
            action_combo.set_selected(actions.index(preset.input_post_action))
        action_combo.connect("notify::selected", self._on_action_changed, actions)
        action_box.append(action_combo)
        self.append(action_box)

        # Output template
        tmpl_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        tmpl_box.append(Gtk.Label(label="Output template:", xalign=0))
        self.tmpl_entry = Gtk.Entry(text=preset.output_template, hexpand=True)
        self.tmpl_entry.set_tooltip_text("Variables: (p) path, (f) filename, (o) output ext, (i) input ext")
        self.tmpl_entry.connect("changed", self._on_template_changed)
        tmpl_box.append(self.tmpl_entry)
        self.append(tmpl_box)

    def _on_name_changed(self, entry):
        self.preset.name = entry.get_text()
        self._on_change()

    def _on_output_changed(self, combo, _pspec):
        idx = combo.get_selected()
        if 0 <= idx < len(OUTPUT_TYPES):
            self.preset.output_type = OUTPUT_TYPES[idx]
            self._on_change()

    def _on_input_toggled(self, check, ext):
        if check.get_active():
            if ext not in self.preset.input_types:
                self.preset.input_types.append(ext)
        else:
            if ext in self.preset.input_types:
                self.preset.input_types.remove(ext)
        self._on_change()

    def _on_setting_bool(self, check, key):
        self.preset.settings[key] = check.get_active()
        self._on_change()

    def _on_setting_spin(self, spin, key):
        self.preset.settings[key] = spin.get_value()
        self._on_change()

    def _on_setting_combo(self, combo, _pspec, key, values):
        idx = combo.get_selected()
        if 0 <= idx < len(values):
            self.preset.settings[key] = values[idx]
            self._on_change()

    def _on_action_changed(self, combo, _pspec, actions):
        idx = combo.get_selected()
        if 0 <= idx < len(actions):
            self.preset.input_post_action = actions[idx]
            self._on_change()

    def _on_template_changed(self, entry):
        self.preset.output_template = entry.get_text()
        self._on_change()


class SettingsWindow(Gtk.ApplicationWindow):
    def __init__(self, app, settings: Settings):
        super().__init__(application=app, title="File Converter — Settings",
                         default_width=800, default_height=600)
        self.settings = settings
        self._modified = False

        header = Gtk.HeaderBar()
        self.set_titlebar(header)

        save_btn = Gtk.Button(label="Save")
        save_btn.add_css_class("suggested-action")
        save_btn.connect("clicked", self._on_save)
        header.pack_end(save_btn)

        # Main layout: sidebar + editor
        paned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        paned.set_position(220)

        # Left: preset list
        left_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)

        # Global settings
        global_frame = Gtk.Frame(label="Global")
        global_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        global_box.set_margin_start(8)
        global_box.set_margin_end(8)
        global_box.set_margin_top(4)
        global_box.set_margin_bottom(4)

        max_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        max_box.append(Gtk.Label(label="Max jobs:", xalign=0, hexpand=True))
        adj = Gtk.Adjustment(value=settings.max_simultaneous_conversions,
                             lower=1, upper=16, step_increment=1)
        self.max_spin = Gtk.SpinButton(adjustment=adj, digits=0)
        self.max_spin.connect("value-changed", self._on_max_changed)
        max_box.append(self.max_spin)
        global_box.append(max_box)

        self.exit_check = Gtk.CheckButton(label="Auto-close when done",
                                          active=settings.exit_when_done)
        self.exit_check.connect("toggled", self._on_exit_toggled)
        global_box.append(self.exit_check)

        # Hardware acceleration
        hw_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        hw_box.append(Gtk.Label(label="GPU accel:", xalign=0, hexpand=True))
        hw_labels = ["Off", "Auto-detect", "NVENC (NVIDIA)", "VAAPI (AMD/Intel)"]
        self.hw_combo = Gtk.DropDown.new_from_strings(hw_labels)
        if settings.hardware_acceleration in HWACCEL_MODES:
            self.hw_combo.set_selected(HWACCEL_MODES.index(settings.hardware_acceleration))
        self.hw_combo.connect("notify::selected", self._on_hw_changed)
        hw_box.append(self.hw_combo)
        global_box.append(hw_box)

        global_frame.set_child(global_box)
        left_box.append(global_frame)

        # Preset list
        left_box.append(Gtk.Label(label="Presets", xalign=0, margin_start=8, margin_top=8))
        scroll = Gtk.ScrolledWindow(vexpand=True)
        self.preset_listbox = Gtk.ListBox()
        self.preset_listbox.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.preset_listbox.connect("row-selected", self._on_preset_selected)
        scroll.set_child(self.preset_listbox)
        left_box.append(scroll)

        # Add/Remove buttons
        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        btn_box.set_margin_start(8)
        btn_box.set_margin_end(8)
        btn_box.set_margin_bottom(8)
        add_btn = Gtk.Button(label="Add")
        add_btn.connect("clicked", self._on_add_preset)
        btn_box.append(add_btn)
        remove_btn = Gtk.Button(label="Remove")
        remove_btn.add_css_class("destructive-action")
        remove_btn.connect("clicked", self._on_remove_preset)
        btn_box.append(remove_btn)
        left_box.append(btn_box)

        paned.set_start_child(left_box)

        # Right: editor
        self.editor_scroll = Gtk.ScrolledWindow(hexpand=True, vexpand=True)
        self.editor_placeholder = Gtk.Label(label="Select a preset to edit")
        self.editor_scroll.set_child(self.editor_placeholder)
        paned.set_end_child(self.editor_scroll)

        self.set_child(paned)
        self._refresh_preset_list()

    def _refresh_preset_list(self):
        while True:
            row = self.preset_listbox.get_row_at_index(0)
            if row is None:
                break
            self.preset_listbox.remove(row)

        for preset in self.settings.presets:
            label = Gtk.Label(label=preset.name, xalign=0, margin_start=8, margin_end=8,
                              margin_top=4, margin_bottom=4)
            self.preset_listbox.append(label)

    def _on_preset_selected(self, listbox, row):
        if row is None:
            self.editor_scroll.set_child(self.editor_placeholder)
            return
        idx = row.get_index()
        if 0 <= idx < len(self.settings.presets):
            editor = PresetEditor(self.settings.presets[idx], self._mark_modified)
            self.editor_scroll.set_child(editor)

    def _on_add_preset(self, _btn):
        new_preset = ConversionPreset(
            name="New Preset",
            output_type="mp4",
            input_types=["avi", "mkv", "mov", "mp4", "webm"],
            settings={"enable_audio": True, "video_quality": 28, "video_encoding_speed": "medium",
                       "audio_bitrate": 155, "video_scale": 1.0},
        )
        self.settings.presets.append(new_preset)
        self._refresh_preset_list()
        self._mark_modified()

    def _on_remove_preset(self, _btn):
        row = self.preset_listbox.get_selected_row()
        if row is not None:
            idx = row.get_index()
            if 0 <= idx < len(self.settings.presets):
                self.settings.presets.pop(idx)
                self._refresh_preset_list()
                self.editor_scroll.set_child(self.editor_placeholder)
                self._mark_modified()

    def _on_max_changed(self, spin):
        self.settings.max_simultaneous_conversions = int(spin.get_value())
        self._mark_modified()

    def _on_exit_toggled(self, check):
        self.settings.exit_when_done = check.get_active()
        self._mark_modified()

    def _on_hw_changed(self, combo, _pspec):
        idx = combo.get_selected()
        if 0 <= idx < len(HWACCEL_MODES):
            self.settings.hardware_acceleration = HWACCEL_MODES[idx]
            self._mark_modified()

    def _on_save(self, _btn):
        save_settings(self.settings)
        self._modified = False
        self.set_title("File Converter — Settings (saved)")
        GLib.timeout_add(GLib.PRIORITY_DEFAULT, 2000, lambda: self.set_title("File Converter — Settings") or False)

    def _mark_modified(self):
        self._modified = True
        self.set_title("File Converter — Settings *")


class SettingsApp(Adw.Application):
    def __init__(self):
        super().__init__(application_id="org.fileconverter.settings")
        self.connect("activate", self._on_activate)

    def _on_activate(self, _app):
        settings = load_settings()
        win = SettingsWindow(self, settings)
        win.present()


def run_settings():
    app = SettingsApp()
    app.run(None)


if __name__ == "__main__":
    run_settings()

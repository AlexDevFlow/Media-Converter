"""GTK 4 settings window — preset editor."""

from __future__ import annotations
import os

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, GLib, Gio

from fileconverter.config import load_settings, save_settings, Settings, HWACCEL_MODES
from fileconverter.helpers import ALL_INPUT_EXTENSIONS, OUTPUT_TYPES, VIDEO_CODECS
from fileconverter import i18n
from fileconverter.i18n import _
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
        name_box.append(Gtk.Label(label=_("Name:"), xalign=0))
        self.name_entry = Gtk.Entry(text=preset.name, hexpand=True)
        self.name_entry.connect("changed", self._on_name_changed)
        name_box.append(self.name_entry)
        self.append(name_box)

        # Output type
        out_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        out_box.append(Gtk.Label(label=_("Output:"), xalign=0))
        self.output_combo = Gtk.DropDown.new_from_strings(OUTPUT_TYPES)
        if preset.output_type in OUTPUT_TYPES:
            self.output_combo.set_selected(OUTPUT_TYPES.index(preset.output_type))
        self.output_combo.connect("notify::selected", self._on_output_changed)
        out_box.append(self.output_combo)
        self.append(out_box)

        # Input types
        self.append(Gtk.Label(label=_("Input types:"), xalign=0))
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
        self.append(Gtk.Label(label=_("Conversion settings:"), xalign=0))

        settings_grid = Gtk.Grid(column_spacing=12, row_spacing=6)
        row = 0

        # Common settings
        common_settings = [
            ("video_codec", _("Video Codec"), None, None, None),
            ("video_quality", _("Video Quality (0-63)"), 0, 63, 28),
            ("video_encoding_speed", _("Encoding Speed"), None, None, None),
            ("video_scale", _("Video Scale"), 0.1, 4.0, 1.0),
            ("video_rotation", _("Rotation (degrees)"), 0, 270, 0),
            ("audio_bitrate", _("Audio Bitrate"), 16, 500, 155),
            ("image_quality", _("Image Quality (0-100)"), 0, 100, 85),
            ("image_scale", _("Image Scale"), 0.1, 4.0, 1.0),
            ("enable_audio", _("Enable Audio"), None, None, True),
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
            elif key == "video_codec":
                combo = Gtk.DropDown.new_from_strings(VIDEO_CODECS)
                curr_codec = str(current or "h264").lower()
                if curr_codec in ("h265", "hevc"):
                    curr_codec = "hevc"
                if curr_codec in VIDEO_CODECS:
                    combo.set_selected(VIDEO_CODECS.index(curr_codec))
                combo.connect("notify::selected", self._on_setting_combo, key, VIDEO_CODECS)
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
        action_box.append(Gtk.Label(label=_("After conversion:"), xalign=0))
        actions = ["none", "archive", "delete"]
        action_combo = Gtk.DropDown.new_from_strings(actions)
        if preset.input_post_action in actions:
            action_combo.set_selected(actions.index(preset.input_post_action))
        action_combo.connect("notify::selected", self._on_action_changed, actions)
        action_box.append(action_combo)
        self.append(action_box)

        # Output template
        tmpl_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        tmpl_box.append(Gtk.Label(label=_("Output template:"), xalign=0))
        self.tmpl_entry = Gtk.Entry(text=preset.output_template, hexpand=True)
        self.tmpl_entry.set_tooltip_text(_("Variables: (p) path, (f) filename, (o) output ext, (i) input ext"))
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
        super().__init__(application=app, title=_("File Converter — Settings"),
                         default_width=800, default_height=600)
        self.settings = settings
        self._modified = False

        header = Gtk.HeaderBar()
        self.set_titlebar(header)

        save_btn = Gtk.Button(label=_("Save"))
        save_btn.add_css_class("suggested-action")
        save_btn.connect("clicked", self._on_save)
        header.pack_end(save_btn)

        # Main layout: sidebar + editor
        paned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        paned.set_position(260)

        # Left: preset list
        left_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)

        # Global settings — each row stacks label above its control so long
        # translated labels don't push the control out of view.
        global_frame = Gtk.Frame(label=_("Global"))
        global_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        global_box.set_margin_start(8)
        global_box.set_margin_end(8)
        global_box.set_margin_top(6)
        global_box.set_margin_bottom(6)

        def _row(label_text: str, control: Gtk.Widget) -> Gtk.Box:
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            lbl = Gtk.Label(label=label_text, xalign=0, wrap=True)
            lbl.add_css_class("dim-label")
            box.append(lbl)
            control.set_hexpand(True)
            box.append(control)
            return box

        self._max_adj = Gtk.Adjustment(value=settings.max_simultaneous_conversions,
                                       lower=1, upper=16, step_increment=1,
                                       page_increment=1)
        self.max_spin = Gtk.SpinButton(adjustment=self._max_adj, digits=0,
                                       numeric=True, climb_rate=1)
        self.max_spin.set_value(settings.max_simultaneous_conversions)
        self.max_spin.connect("value-changed", self._on_max_changed)
        global_box.append(_row(_("Max jobs:"), self.max_spin))

        self.exit_check = Gtk.CheckButton(active=settings.exit_when_done)
        self.exit_check.set_child(Gtk.Label(label=_("Auto-close when done"),
                                            xalign=0, wrap=True, hexpand=True))
        self.exit_check.connect("toggled", self._on_exit_toggled)
        global_box.append(self.exit_check)

        # Hardware acceleration (labels index-aligned with HWACCEL_MODES)
        from fileconverter.config import HWACCEL_LABELS
        hw_labels = [_(label) for label in HWACCEL_LABELS]
        self.hw_combo = Gtk.DropDown.new_from_strings(hw_labels)
        if settings.hardware_acceleration in HWACCEL_MODES:
            self.hw_combo.set_selected(HWACCEL_MODES.index(settings.hardware_acceleration))
        self.hw_combo.connect("notify::selected", self._on_hw_changed)
        global_box.append(_row(_("GPU accel:"), self.hw_combo))

        # Language
        detected = i18n.detect_system_language() or ""
        detected_label = dict(i18n.SUPPORTED_LANGUAGES).get(detected)
        auto_label = (
            _("System default ({name})").format(name=detected_label)
            if detected_label else _("System default")
        )
        lang_labels = [auto_label] + [
            label for code, label in i18n.SUPPORTED_LANGUAGES if code != "auto"
        ]
        self.lang_combo = Gtk.DropDown.new_from_strings(lang_labels)
        current_lang = settings.language if settings.language in i18n.LANGUAGE_CODES else "auto"
        try:
            self.lang_combo.set_selected(i18n.LANGUAGE_CODES.index(current_lang))
        except ValueError:
            self.lang_combo.set_selected(0)
        self.lang_combo.connect("notify::selected", self._on_lang_changed)
        global_box.append(_row(_("Language:"), self.lang_combo))

        global_frame.set_child(global_box)
        left_box.append(global_frame)

        # Preset list
        left_box.append(Gtk.Label(label=_("Presets"), xalign=0, margin_start=8, margin_top=8))
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
        add_btn = Gtk.Button(label=_("Add"))
        add_btn.connect("clicked", self._on_add_preset)
        btn_box.append(add_btn)
        remove_btn = Gtk.Button(label=_("Remove"))
        remove_btn.add_css_class("destructive-action")
        remove_btn.connect("clicked", self._on_remove_preset)
        btn_box.append(remove_btn)
        left_box.append(btn_box)

        left_box.set_size_request(240, -1)
        paned.set_start_child(left_box)
        paned.set_shrink_start_child(False)

        # Right: editor
        self.editor_scroll = Gtk.ScrolledWindow(hexpand=True, vexpand=True)
        self.editor_placeholder = Gtk.Label(label=_("Select a preset to edit"))
        self.editor_scroll.set_child(self.editor_placeholder)
        paned.set_end_child(self.editor_scroll)

        self.set_child(paned)
        self._refresh_preset_list()
        # Prevent the SpinButton from grabbing initial focus
        self.preset_listbox.grab_focus()

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
            name=_("New Preset"),
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

    def _on_lang_changed(self, combo, _pspec):
        idx = combo.get_selected()
        if not (0 <= idx < len(i18n.LANGUAGE_CODES)):
            return
        code = i18n.LANGUAGE_CODES[idx]
        if code == self.settings.language:
            return
        self.settings.language = code
        save_settings(self.settings)
        self._modified = False
        i18n.init(code)
        app = self.get_application()
        # Rebuild the window so every label picks up the new language.
        new_win = SettingsWindow(app, self.settings)
        new_win.present()
        self.close()

    def _on_save(self, _btn):
        save_settings(self.settings)
        self._modified = False
        self.set_title(_("File Converter — Settings (saved)"))
        GLib.timeout_add(2000, lambda: self.set_title(_("File Converter — Settings")) or False)

    def _mark_modified(self):
        self._modified = True
        self.set_title(_("File Converter — Settings *"))


class SettingsApp(Adw.Application):
    def __init__(self):
        super().__init__(
            application_id="org.fileconverter.settings",
            flags=Gio.ApplicationFlags.NON_UNIQUE,
        )
        self.connect("activate", self._on_activate)

    def _on_activate(self, _app):
        settings = load_settings()
        i18n.init(settings.language)
        win = SettingsWindow(self, settings)
        win.present()


def run_settings():
    app = SettingsApp()
    app.run(None)


if __name__ == "__main__":
    run_settings()

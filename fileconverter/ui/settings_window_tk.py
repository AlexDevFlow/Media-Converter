"""tkinter settings window — feature-parity port of settings_window.py (GTK).

Same layout: global settings + preset list on the left, per-preset editor on
the right. On macOS, saving also regenerates the Finder Quick Actions so the
context menu never drifts out of sync with the presets (GH #7).
"""

from __future__ import annotations
import sys
import tkinter as tk
from tkinter import ttk

from fileconverter.config import (
    HWACCEL_LABELS, HWACCEL_MODES, Settings, load_settings, save_settings,
)
from fileconverter.helpers import ALL_INPUT_EXTENSIONS, OUTPUT_TYPES, VIDEO_CODECS
from fileconverter import i18n
from fileconverter.i18n import _
from fileconverter.presets import ConversionPreset

_SPEEDS = ["ultrafast", "superfast", "veryfast", "faster", "fast",
           "medium", "slow", "slower", "veryslow"]
_POST_ACTIONS = ["none", "archive", "delete"]


class PresetEditor(ttk.Frame):
    """Editor panel for a single preset."""

    def __init__(self, parent, preset: ConversionPreset, on_change):
        super().__init__(parent, padding=12)
        self.preset = preset
        self._on_change = on_change
        self.columnconfigure(1, weight=1)
        row = 0

        # Name
        ttk.Label(self, text=_("Name:")).grid(row=row, column=0, sticky="w")
        self.name_var = tk.StringVar(value=preset.name)
        self.name_var.trace_add("write", self._on_name_changed)
        ttk.Entry(self, textvariable=self.name_var).grid(
            row=row, column=1, sticky="ew", pady=2)
        row += 1

        # Output type
        ttk.Label(self, text=_("Output:")).grid(row=row, column=0, sticky="w")
        self.output_var = tk.StringVar(
            value=preset.output_type if preset.output_type in OUTPUT_TYPES else "mp4")
        out_menu = ttk.Combobox(self, textvariable=self.output_var,
                                values=OUTPUT_TYPES, state="readonly", width=10)
        out_menu.grid(row=row, column=1, sticky="w", pady=2)
        out_menu.bind("<<ComboboxSelected>>", self._on_output_changed)
        row += 1

        # Input types (checkbox grid)
        ttk.Label(self, text=_("Input types:")).grid(
            row=row, column=0, columnspan=2, sticky="w", pady=(8, 2))
        row += 1
        grid = ttk.Frame(self)
        grid.grid(row=row, column=0, columnspan=2, sticky="ew")
        self._input_vars = {}
        per_row = 8
        for i, ext in enumerate(ALL_INPUT_EXTENSIONS):
            var = tk.BooleanVar(value=ext in preset.input_types)
            var.trace_add("write",
                          lambda *a, e=ext, v=var: self._on_input_toggled(e, v))
            self._input_vars[ext] = var
            ttk.Checkbutton(grid, text=ext, variable=var).grid(
                row=i // per_row, column=i % per_row, sticky="w", padx=2)
        row += 1

        # Conversion settings
        ttk.Separator(self, orient="horizontal").grid(
            row=row, column=0, columnspan=2, sticky="ew", pady=8)
        row += 1
        ttk.Label(self, text=_("Conversion settings:")).grid(
            row=row, column=0, columnspan=2, sticky="w", pady=(0, 4))
        row += 1

        # (key, label, min, max, default) — mirrors the GTK editor exactly.
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
            ttk.Label(self, text=label).grid(row=row, column=0, sticky="w", pady=1)
            current = preset.settings.get(key, default)

            if isinstance(default, bool) or key == "enable_audio":
                var = tk.BooleanVar(value=bool(current) if current is not None else True)
                var.trace_add("write",
                              lambda *a, k=key, v=var: self._set_setting(k, v.get()))
                ttk.Checkbutton(self, variable=var).grid(row=row, column=1, sticky="w")
            elif key == "video_encoding_speed":
                var = tk.StringVar(value=str(current or "medium").lower())
                combo = ttk.Combobox(self, textvariable=var, values=_SPEEDS,
                                     state="readonly", width=12)
                combo.grid(row=row, column=1, sticky="w", pady=1)
                combo.bind("<<ComboboxSelected>>",
                           lambda e, k=key, v=var: self._set_setting(k, v.get()))
            elif key == "video_codec":
                curr = str(current or "h264").lower()
                if curr == "h265":
                    curr = "hevc"
                var = tk.StringVar(value=curr if curr in VIDEO_CODECS else "h264")
                combo = ttk.Combobox(self, textvariable=var, values=VIDEO_CODECS,
                                     state="readonly", width=12)
                combo.grid(row=row, column=1, sticky="w", pady=1)
                combo.bind("<<ComboboxSelected>>",
                           lambda e, k=key, v=var: self._set_setting(k, v.get()))
            else:
                is_float = isinstance(default, float)
                val = float(current) if current is not None else float(default)
                var = tk.StringVar(value=f"{val:g}")
                spin = ttk.Spinbox(
                    self, textvariable=var, from_=float(min_val), to=float(max_val),
                    increment=0.1 if is_float else 1, width=10,
                    command=lambda k=key, v=var, f=is_float: self._on_spin(k, v, f))
                spin.grid(row=row, column=1, sticky="w", pady=1)
                var.trace_add("write",
                              lambda *a, k=key, v=var, f=is_float: self._on_spin(k, v, f))
            row += 1

        # Post-conversion action
        ttk.Label(self, text=_("After conversion:")).grid(
            row=row, column=0, sticky="w", pady=(8, 1))
        self.action_var = tk.StringVar(
            value=preset.input_post_action
            if preset.input_post_action in _POST_ACTIONS else "none")
        action = ttk.Combobox(self, textvariable=self.action_var,
                              values=_POST_ACTIONS, state="readonly", width=12)
        action.grid(row=row, column=1, sticky="w", pady=(8, 1))
        action.bind("<<ComboboxSelected>>", self._on_action_changed)
        row += 1

        # Output template
        ttk.Label(self, text=_("Output template:")).grid(row=row, column=0, sticky="w")
        self.tmpl_var = tk.StringVar(value=preset.output_template)
        self.tmpl_var.trace_add("write", self._on_template_changed)
        ttk.Entry(self, textvariable=self.tmpl_var).grid(
            row=row, column=1, sticky="ew", pady=2)
        row += 1
        ttk.Label(
            self, foreground="gray",
            text=_("Variables: (p) path, (f) filename, (o) output ext, (i) input ext"),
        ).grid(row=row, column=0, columnspan=2, sticky="w")

    def _on_name_changed(self, *args):
        self.preset.name = self.name_var.get()
        self._on_change()

    def _on_output_changed(self, _event=None):
        self.preset.output_type = self.output_var.get()
        self._on_change()

    def _on_input_toggled(self, ext: str, var: tk.BooleanVar):
        if var.get():
            if ext not in self.preset.input_types:
                self.preset.input_types.append(ext)
        else:
            if ext in self.preset.input_types:
                self.preset.input_types.remove(ext)
        self._on_change()

    def _set_setting(self, key: str, value):
        self.preset.settings[key] = value
        self._on_change()

    def _on_spin(self, key: str, var: tk.StringVar, is_float: bool):
        try:
            value = float(var.get())
        except ValueError:
            return  # mid-edit, e.g. empty field
        self._set_setting(key, value if is_float else int(value))

    def _on_action_changed(self, _event=None):
        self.preset.input_post_action = self.action_var.get()
        self._on_change()

    def _on_template_changed(self, *args):
        self.preset.output_template = self.tmpl_var.get()
        self._on_change()


class SettingsWindow:
    def __init__(self, root: tk.Tk, settings: Settings):
        self.root = root
        self.settings = settings
        self._modified = False
        self._editor = None

        root.title(_("File Converter — Settings"))
        root.geometry("860x620")
        root.minsize(720, 480)

        paned = ttk.Panedwindow(root, orient="horizontal")
        paned.pack(fill="both", expand=True)

        # ── Left: global settings + preset list ──
        left = ttk.Frame(paned, padding=8)
        paned.add(left, weight=0)

        glob = ttk.Labelframe(left, text=_("Global"), padding=8)
        glob.pack(fill="x")
        glob.columnconfigure(1, weight=1)

        ttk.Label(glob, text=_("Max jobs:")).grid(row=0, column=0, sticky="w")
        self.max_var = tk.StringVar(value=str(settings.max_simultaneous_conversions))
        self.max_var.trace_add("write", self._on_max_changed)
        ttk.Spinbox(glob, textvariable=self.max_var, from_=1, to=16, width=6).grid(
            row=0, column=1, sticky="w", pady=2)

        self.exit_var = tk.BooleanVar(value=settings.exit_when_done)
        self.exit_var.trace_add("write", self._on_exit_toggled)
        ttk.Checkbutton(glob, text=_("Auto-close when done"),
                        variable=self.exit_var).grid(
            row=1, column=0, columnspan=2, sticky="w", pady=2)

        ttk.Label(glob, text=_("GPU accel:")).grid(row=2, column=0, sticky="w")
        hw_labels = [_(label) for label in HWACCEL_LABELS]
        current_hw = (settings.hardware_acceleration
                      if settings.hardware_acceleration in HWACCEL_MODES else "off")
        self.hw_var = tk.StringVar(value=hw_labels[HWACCEL_MODES.index(current_hw)])
        hw_combo = ttk.Combobox(glob, textvariable=self.hw_var, values=hw_labels,
                                state="readonly", width=20)
        hw_combo.grid(row=2, column=1, sticky="w", pady=2)
        hw_combo.bind("<<ComboboxSelected>>",
                      lambda e: self._on_hw_changed(hw_labels))

        ttk.Label(glob, text=_("Language:")).grid(row=3, column=0, sticky="w")
        detected = i18n.detect_system_language() or ""
        detected_label = dict(i18n.SUPPORTED_LANGUAGES).get(detected)
        auto_label = (_("System default ({name})").format(name=detected_label)
                      if detected_label else _("System default"))
        self._lang_labels = [auto_label] + [
            label for code, label in i18n.SUPPORTED_LANGUAGES if code != "auto"]
        current_lang = (settings.language
                        if settings.language in i18n.LANGUAGE_CODES else "auto")
        self.lang_var = tk.StringVar(
            value=self._lang_labels[i18n.LANGUAGE_CODES.index(current_lang)])
        lang_combo = ttk.Combobox(glob, textvariable=self.lang_var,
                                  values=self._lang_labels, state="readonly", width=20)
        lang_combo.grid(row=3, column=1, sticky="w", pady=2)
        lang_combo.bind("<<ComboboxSelected>>", self._on_lang_changed)

        ttk.Label(left, text=_("Presets")).pack(anchor="w", pady=(8, 2))
        list_frame = ttk.Frame(left)
        list_frame.pack(fill="both", expand=True)
        self.preset_list = tk.Listbox(list_frame, exportselection=False)
        list_scroll = ttk.Scrollbar(list_frame, orient="vertical",
                                    command=self.preset_list.yview)
        self.preset_list.configure(yscrollcommand=list_scroll.set)
        self.preset_list.pack(side="left", fill="both", expand=True)
        list_scroll.pack(side="right", fill="y")
        self.preset_list.bind("<<ListboxSelect>>", self._on_preset_selected)

        btns = ttk.Frame(left)
        btns.pack(fill="x", pady=(4, 0))
        ttk.Button(btns, text=_("Add"), command=self._on_add_preset).pack(
            side="left", padx=(0, 4))
        ttk.Button(btns, text=_("Remove"), command=self._on_remove_preset).pack(
            side="left")
        ttk.Button(btns, text=_("Save"), command=self._on_save).pack(side="right")

        # ── Right: scrollable editor ──
        right = ttk.Frame(paned)
        paned.add(right, weight=1)
        self.editor_canvas = tk.Canvas(right, highlightthickness=0)
        editor_scroll = ttk.Scrollbar(right, orient="vertical",
                                      command=self.editor_canvas.yview)
        self.editor_canvas.configure(yscrollcommand=editor_scroll.set)
        self.editor_canvas.pack(side="left", fill="both", expand=True)
        editor_scroll.pack(side="right", fill="y")
        self._canvas_item = None
        self.editor_canvas.bind(
            "<Configure>",
            lambda e: self._canvas_item and self.editor_canvas.itemconfigure(
                self._canvas_item, width=e.width))

        self._placeholder()
        self._refresh_preset_list()

    # ── Left panel handlers ──

    def _refresh_preset_list(self):
        self.preset_list.delete(0, "end")
        for preset in self.settings.presets:
            self.preset_list.insert("end", preset.name)

    def _selected_index(self):
        sel = self.preset_list.curselection()
        return sel[0] if sel else None

    def _placeholder(self):
        self._set_editor(ttk.Label(self.editor_canvas,
                                   text=_("Select a preset to edit"), padding=20))

    def _set_editor(self, widget):
        if self._canvas_item is not None:
            self.editor_canvas.delete(self._canvas_item)
        self._editor = widget
        self._canvas_item = self.editor_canvas.create_window(
            (0, 0), window=widget, anchor="nw",
            width=max(self.editor_canvas.winfo_width(), 400))
        widget.bind(
            "<Configure>",
            lambda e: self.editor_canvas.configure(
                scrollregion=self.editor_canvas.bbox("all")))

    def _on_preset_selected(self, _event=None):
        idx = self._selected_index()
        if idx is None or not (0 <= idx < len(self.settings.presets)):
            return
        self._set_editor(PresetEditor(self.editor_canvas,
                                      self.settings.presets[idx],
                                      self._mark_modified))

    def _on_add_preset(self):
        new_preset = ConversionPreset(
            name=_("New Preset"),
            output_type="mp4",
            input_types=["avi", "mkv", "mov", "mp4", "webm"],
            settings={"enable_audio": True, "video_quality": 28,
                      "video_encoding_speed": "medium",
                      "audio_bitrate": 155, "video_scale": 1.0},
        )
        self.settings.presets.append(new_preset)
        self._refresh_preset_list()
        self.preset_list.selection_clear(0, "end")
        self.preset_list.selection_set("end")
        self.preset_list.see("end")
        self._on_preset_selected()
        self._mark_modified()

    def _on_remove_preset(self):
        idx = self._selected_index()
        if idx is not None and 0 <= idx < len(self.settings.presets):
            self.settings.presets.pop(idx)
            self._refresh_preset_list()
            self._placeholder()
            self._mark_modified()

    def _on_max_changed(self, *args):
        try:
            self.settings.max_simultaneous_conversions = max(
                1, min(16, int(self.max_var.get())))
            self._mark_modified()
        except ValueError:
            pass

    def _on_exit_toggled(self, *args):
        self.settings.exit_when_done = self.exit_var.get()
        self._mark_modified()

    def _on_hw_changed(self, hw_labels):
        try:
            idx = hw_labels.index(self.hw_var.get())
        except ValueError:
            return
        self.settings.hardware_acceleration = HWACCEL_MODES[idx]
        self._mark_modified()

    def _on_lang_changed(self, _event=None):
        try:
            idx = self._lang_labels.index(self.lang_var.get())
        except ValueError:
            return
        code = i18n.LANGUAGE_CODES[idx]
        if code == self.settings.language:
            return
        self.settings.language = code
        save_settings(self.settings)
        self._modified = False
        i18n.init(code)
        # Rebuild the window so every label picks up the new language.
        for child in self.root.winfo_children():
            child.destroy()
        SettingsWindow(self.root, self.settings)

    def _on_save(self):
        save_settings(self.settings)
        self._modified = False
        if sys.platform == "darwin":
            # Keep the Finder context menu in sync with the presets (GH #7).
            try:
                from fileconverter.integration.macos import refresh_services
                refresh_services(quiet=True)
            except Exception:
                pass
        self.root.title(_("File Converter — Settings (saved)"))
        self.root.after(2000,
                        lambda: self.root.title(_("File Converter — Settings")))
        self._refresh_preset_list()

    def _mark_modified(self):
        self._modified = True
        self.root.title(_("File Converter — Settings *"))


def run_settings() -> None:
    root = tk.Tk()
    settings = load_settings()
    i18n.init(settings.language)

    if sys.platform == "darwin":
        try:
            root.lift()
            root.attributes("-topmost", True)
            root.after(700, lambda: root.attributes("-topmost", False))
        except tk.TclError:
            pass

    SettingsWindow(root, settings)
    root.mainloop()


if __name__ == "__main__":
    run_settings()

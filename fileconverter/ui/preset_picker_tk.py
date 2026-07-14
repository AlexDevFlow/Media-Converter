"""tkinter preset picker — feature-parity port of preset_picker.py (GTK).

Shows a filtered list of compatible presets for the selected files. On macOS
this backs the generic "File Converter…" Quick Action; on Linux it serves
file managers without submenu support when GTK is missing.

Usage: fileconverter-pick file1.avi file2.mkv
"""

from __future__ import annotations
import os
import shutil
import subprocess
import sys
import tkinter as tk
from tkinter import messagebox, ttk

from fileconverter import i18n
from fileconverter.i18n import _


def _find_fileconverter() -> str | None:
    for path in [
        os.path.expanduser("~/.local/bin/fileconverter"),
        "/usr/local/bin/fileconverter",
        "/usr/bin/fileconverter",
    ]:
        if os.path.isfile(path) and os.access(path, os.X_OK):
            return path
    return shutil.which("fileconverter")


class PresetPickerWindow:
    def __init__(self, root: tk.Tk, file_paths: list, presets: list):
        self.root = root
        self.file_paths = file_paths
        self.presets = presets

        root.title(_("File Converter — Select Preset"))
        root.geometry("420x520")
        root.minsize(360, 300)

        n = len(file_paths)
        if n == 1:
            info_text = _("{count} file selected").format(count=n)
        else:
            info_text = _("{count} files selected").format(count=n)
        ttk.Label(root, text=info_text, foreground="gray",
                  padding=(12, 10, 12, 6)).pack(anchor="w")

        container = ttk.Frame(root)
        container.pack(fill="both", expand=True)
        canvas = tk.Canvas(container, highlightthickness=0)
        scrollbar = ttk.Scrollbar(container, orient="vertical",
                                  command=canvas.yview)
        inner = ttk.Frame(canvas)
        inner.bind("<Configure>",
                   lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        window = canvas.create_window((0, 0), window=inner, anchor="nw")
        canvas.bind("<Configure>",
                    lambda e: canvas.itemconfigure(window, width=e.width))
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        current_folder = None
        for preset_data in presets:
            name = preset_data.get("name", "")
            parts = name.split("/")
            folder = "/".join(parts[:-1]) if len(parts) > 1 else ""
            short_name = parts[-1]

            if folder and folder != current_folder:
                current_folder = folder
                ttk.Label(inner, text=folder, padding=(12, 8, 12, 2)).pack(anchor="w")

            row = ttk.Frame(inner, padding=(12, 3))
            row.pack(fill="x")
            row.columnconfigure(0, weight=1)
            ttk.Label(row, text=short_name, anchor="w").grid(
                row=0, column=0, sticky="ew")
            ttk.Label(row, text=preset_data.get("output_type", "").upper(),
                      foreground="gray").grid(row=0, column=1, padx=8)
            ttk.Button(row, text=_("Convert"),
                       command=lambda nm=name: self._on_convert(nm)).grid(
                row=0, column=2)

    def _on_convert(self, preset_name: str):
        fc = _find_fileconverter()
        if fc:
            cmd = [fc, "--conversion-preset", preset_name] + self.file_paths
        else:
            cmd = [sys.executable, "-m", "fileconverter",
                   "--conversion-preset", preset_name] + self.file_paths
        subprocess.Popen(cmd, start_new_session=True)
        self.root.destroy()


def main():
    files = sys.argv[1:]
    if not files:
        print("Usage: fileconverter-pick file1 file2 ...", file=sys.stderr)
        sys.exit(1)
    file_paths = [os.path.abspath(f) for f in files]

    from fileconverter.config import load_settings
    settings = load_settings()
    i18n.init(settings.language)

    extensions = set()
    for f in file_paths:
        ext = os.path.splitext(f)[1]
        if ext:
            extensions.add(ext.lower().lstrip("."))
    compatible = [p.to_dict() for p in settings.presets
                  if all(ext in p.input_types for ext in extensions)]

    root = tk.Tk()
    if sys.platform == "darwin":
        try:
            root.lift()
            root.attributes("-topmost", True)
            root.after(700, lambda: root.attributes("-topmost", False))
        except tk.TclError:
            pass

    if not compatible:
        root.withdraw()
        messagebox.showinfo(
            _("No compatible presets"),
            _("No presets support all selected file types: {types}").format(
                types=", ".join(sorted(extensions))))
        return

    PresetPickerWindow(root, file_paths, compatible)
    root.mainloop()


if __name__ == "__main__":
    main()

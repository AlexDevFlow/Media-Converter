# -*- mode: python ; coding: utf-8 -*-

import glob
import os

_locale_datas = [(p, f"locales/{p.split('/')[-3]}/LC_MESSAGES") for p in glob.glob('fileconverter/locales/*/LC_MESSAGES/fileconverter.mo')]

# GIR typelibs — PyInstaller's auto-discovery fails on Ubuntu 24.04 with
# libgirepository-2.0 installed, leaving the bundle without GLib/Gtk/Adw
# typelibs and causing every GTK call to silently no-op at runtime.
# Bundle them explicitly from the system path; the binary loader expects
# them under gi_typelibs/ inside the frozen archive.
_gi_typelib_dirs = [
    "/usr/lib/x86_64-linux-gnu/girepository-1.0",
    "/usr/lib64/girepository-1.0",
    "/usr/lib/girepository-1.0",
]
_gi_typelib_datas = []
for _d in _gi_typelib_dirs:
    if os.path.isdir(_d):
        _gi_typelib_datas = [(p, "gi_typelibs") for p in glob.glob(os.path.join(_d, "*.typelib"))]
        break

# GTK4 + libadwaita + Cairo + Pango shared libraries — PyInstaller's gi
# hook only bundles the core GLib/Gio/GObject libs; the actual GTK
# rendering stack has to be collected explicitly or the frozen binary
# can never open a window. Use collect_dynamic_libs for completeness.
from PyInstaller.utils.hooks import collect_dynamic_libs, collect_data_files
_gi_binaries = []
for _mod in ("gi", "cairo"):
    _gi_binaries += collect_dynamic_libs(_mod)

# Pull in GTK/Adw shared libraries directly — the gi hook does not detect
# them as Python-side dependencies, so we ldconfig-walk the system path.
import subprocess as _sp
_lib_search = "/usr/lib/x86_64-linux-gnu"
_gtk_lib_patterns = [
    "libgtk-4.so*", "libadwaita-1.so*", "libgdk_pixbuf-2.0.so*",
    "libcairo.so*", "libcairo-gobject.so*",
    "libpango-1.0.so*", "libpangocairo-1.0.so*", "libpangoft2-1.0.so*",
    "libharfbuzz.so*", "libharfbuzz-gobject.so*",
    "libfreetype.so*", "libfontconfig.so*",
    "libgirepository-1.0.so*",
    "libepoxy.so*", "libgraphene-1.0.so*",
    "libfribidi.so*", "libthai.so*", "libdatrie.so*",
    "libappstream.so*",
]
_extra_binaries = []
if os.path.isdir(_lib_search):
    for _pat in _gtk_lib_patterns:
        for _p in glob.glob(os.path.join(_lib_search, _pat)):
            if os.path.isfile(_p) and not os.path.islink(_p):
                _extra_binaries.append((_p, "."))

a = Analysis(
    ['fileconverter/__main__.py'],
    pathex=[],
    binaries=_gi_binaries + _extra_binaries,
    datas=[
        ('fileconverter/resources/default_presets.yaml', 'resources'),
        ('fileconverter/resources/fileconverter.desktop', 'resources'),
        ('fileconverter/integration/nautilus_extension.py', 'fileconverter/integration'),
    ] + _locale_datas + _gi_typelib_datas,
    hiddenimports=[
        'fileconverter',
        'fileconverter.cli',
        'fileconverter.config',
        'fileconverter.helpers',
        'fileconverter.i18n',
        'fileconverter.presets',
        'fileconverter.path_helpers',
        'fileconverter.jobs',
        'fileconverter.jobs.base',
        'fileconverter.jobs.factory',
        'fileconverter.jobs.ffmpeg',
        'fileconverter.jobs.gif',
        'fileconverter.jobs.imagemagick',
        'fileconverter.jobs.libreoffice',
        # Sanitises the environment of external tool subprocesses so they
        # don't inherit the bundle's LD_LIBRARY_PATH (GH #6).
        'fileconverter.jobs.proc',
        'fileconverter.ui',
        'fileconverter.ui.progress_window',
        'fileconverter.ui.preset_picker',
        'fileconverter.ui.settings_window',
        'fileconverter.integration',
        'fileconverter.integration.install',
        'fileconverter.integration.nautilus_extension',
        'gi.overrides',
        'gi.overrides.GLib',
        'gi.overrides.GObject',
        'gi.overrides.Gtk',
        'gi.overrides.Gdk',
        'gi.overrides.Gio',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='fileconverter',
    debug=False,
    bootloader_ignore_signals=False,
    strip=True,
    upx=False,
    console=True,
)

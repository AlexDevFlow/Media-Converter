# -*- mode: python ; coding: utf-8 -*-

import glob

_locale_datas = [(p, f"locales/{p.split('/')[-3]}/LC_MESSAGES") for p in glob.glob('locales/*/LC_MESSAGES/fileconverter.mo')]

a = Analysis(
    ['fileconverter/__main__.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('resources/default_presets.yaml', 'resources'),
        ('resources/fileconverter.desktop', 'resources'),
        ('fileconverter/integration/nautilus_extension.py', 'fileconverter/integration'),
    ] + _locale_datas,
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
        'fileconverter.ui',
        'fileconverter.ui.progress_window',
        'fileconverter.ui.preset_picker',
        'fileconverter.ui.settings_window',
        'fileconverter.integration',
        'fileconverter.integration.install',
        'fileconverter.integration.nautilus_extension',
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

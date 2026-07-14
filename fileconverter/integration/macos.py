"""macOS installer — Finder Quick Actions (Services), launchers, Homebrew deps.

Mirrors the Linux installer 1:1 in behaviour, with design choices informed by
the issue tracker of the Linux version:

- One .workflow per preset, scoped to that preset's input types via UTIs
  (NSSendFileTypes), so Finder only offers presets that make sense for the
  selected files — the type-aware grouping proposed for KDE in GH #7.
- Re-installs glob-remove every "File Converter*" workflow first, so renamed
  or deleted presets never leave stale menu entries behind (GH #7).
- Source install into a private venv — no PyInstaller onefile binary, which
  broke on rolling-release libraries (GH #6) and tripped "not authorized to
  execute" quarantine policies (GH #5).
- No GTK anywhere: the GUI is tkinter with a headless fallback (GH #5).
- Launchers export PATH including the Homebrew prefix: Finder services run
  with a minimal environment that would otherwise hide ffmpeg/magick/gs.
"""

from __future__ import annotations
import json
import os
import plistlib
import shlex
import shutil
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

from fileconverter.integration.install import _print

APP_DIR = Path.home() / ".local" / "share" / "fileconverter"
PAYLOAD_DIR = APP_DIR / "app"
VENV_DIR = APP_DIR / "venv"
BIN_DIR = APP_DIR / "bin"
UI_BIN = BIN_DIR / "fileconverter-ui"
MENU_JSON = APP_DIR / "menu.json"
LOCAL_BIN = Path.home() / ".local" / "bin"
SERVICES_DIR = Path.home() / "Library" / "Services"
SETTINGS_APP = Path.home() / "Applications" / "File Converter Settings.app"

# "File Converter.app" hosts the Finder Sync extension (the real right-click
# submenu, like the Dolphin/Nemo submenu on Linux) and doubles as the
# double-clickable settings entry.
HOST_APP = Path.home() / "Applications" / "File Converter.app"
HOST_BUNDLE_ID = "org.fileconverter.app"
EXT_BUNDLE_ID = "org.fileconverter.app.finder-sync"

# Every workflow we create starts with this, so install/uninstall/is_installed
# all agree on one glob and stale actions from earlier versions get cleaned up.
WORKFLOW_GLOB = "File Converter*.workflow"
WORKFLOW_PREFIX = "File Converter - "
PICKER_WORKFLOW_NAME = "File Converter….workflow"
PICKER_MENU_ITEM = "File Converter…"

_SOFFICE_APP_PATHS = [
    "/Applications/LibreOffice.app/Contents/MacOS/soffice",
    str(Path.home() / "Applications" / "LibreOffice.app" / "Contents" / "MacOS" / "soffice"),
]

# Homebrew's install prefix differs between Apple Silicon and Intel.
_BREW_PREFIXES = ["/opt/homebrew/bin", "/usr/local/bin"]


# ── Dependency checking ──

def _brew() -> str | None:
    for prefix in _BREW_PREFIXES:
        p = os.path.join(prefix, "brew")
        if os.path.exists(p):
            return p
    return shutil.which("brew")


_BREW_PACKAGES = {
    "ffmpeg": "ffmpeg",
    "imagemagick": "imagemagick",
    "ghostscript": "ghostscript",
    "libreoffice": "--cask libreoffice",
}


def install_hint(generic: str) -> str:
    """Return a macOS-appropriate install hint for a missing dependency."""
    if _brew() is None:
        return (f"Install Homebrew from https://brew.sh, then run: "
                f"brew install {_BREW_PACKAGES.get(generic, generic)}")
    return f"Install it with: brew install {_BREW_PACKAGES.get(generic, generic)}"


def _which_media_path(cmds: list[str]) -> str | None:
    """shutil.which() plus the Homebrew prefixes, since GUI-launched processes
    (Finder services) don't have Homebrew on PATH."""
    for cmd in cmds:
        found = shutil.which(cmd)
        if found:
            return found
        for prefix in _BREW_PREFIXES:
            p = os.path.join(prefix, cmd)
            if os.path.exists(p) and os.access(p, os.X_OK):
                return p
    return None


def find_soffice() -> str | None:
    found = _which_media_path(["soffice", "libreoffice"])
    if found:
        return found
    for p in _SOFFICE_APP_PATHS:
        if os.path.exists(p):
            return p
    return None


def check_dependencies() -> dict[str, bool]:
    """Check all dependencies, printing an [OK]/[MISSING] line per tool."""
    results = {}
    deps = [
        ("FFmpeg", lambda: _which_media_path(["ffmpeg"]), "ffmpeg"),
        ("ImageMagick", lambda: _which_media_path(["magick", "convert"]), "imagemagick"),
        ("Ghostscript", lambda: _which_media_path(["gs"]), "ghostscript"),
        ("LibreOffice", find_soffice, "libreoffice"),
    ]
    for label, finder, generic in deps:
        found = finder()
        if found:
            _print(f"  [OK] {label}", "green")
            results[label] = True
        else:
            _print(f"  [MISSING] {label} — {install_hint(generic)}", "yellow")
            results[label] = False
    return results


def _missing_required_formulae() -> list[str]:
    """Required (non-optional) Homebrew formulae that are absent."""
    missing = []
    if not _which_media_path(["ffmpeg"]):
        missing.append("ffmpeg")
    if not _which_media_path(["magick", "convert"]):
        missing.append("imagemagick")
    if not _which_media_path(["gs"]):
        missing.append("ghostscript")
    return missing


def _offer_brew_install(missing: list[str]) -> None:
    """Offer to install missing required tools via Homebrew (interactive only)."""
    brew = _brew()
    if not brew:
        _print("\n  Homebrew not found — install it from https://brew.sh, then run:", "yellow")
        _print(f"  brew install {' '.join(missing)}\n", "cyan")
        return

    cmd = f"{brew} install {' '.join(missing)}"
    if not sys.stdin.isatty():
        _print(f"\n  Install missing dependencies with:\n  {cmd}\n", "cyan")
        return

    try:
        answer = input(f"\n  Install missing dependencies now? [{cmd}] [Y/n] ").strip().lower()
    except EOFError:
        answer = "n"
    if answer in ("", "y", "yes", "s", "si", "sì"):
        result = subprocess.run([brew, "install"] + missing)
        if result.returncode == 0:
            _print("  [OK] Dependencies installed", "green")
        else:
            _print("  [WARN] Homebrew reported an error — re-run setup afterwards.", "yellow")
    else:
        _print(f"  Skipped. Install later with: {cmd}", "yellow")


# ── Runtime resolution (which python + package root the launchers embed) ──

def _package_root() -> Path:
    """Directory that contains the `fileconverter` package."""
    return Path(__file__).resolve().parent.parent.parent


def _runtime() -> tuple[str, str]:
    """Return (python_executable, pythonpath_root) for the launcher scripts.

    When running from the canonical installed payload we pin the private venv
    interpreter; a source checkout gets whatever interpreter is running now.
    """
    root = _package_root()
    venv_py = VENV_DIR / "bin" / "python3"
    if root == PAYLOAD_DIR and venv_py.exists():
        return str(venv_py), str(PAYLOAD_DIR)
    return sys.executable or "/usr/bin/python3", str(root)


# ── Launcher scripts ──

def _launcher_path_env() -> str:
    """PATH prefix so services launched by Finder can find the media tools."""
    parts = _BREW_PREFIXES + [str(LOCAL_BIN)]
    return ":".join(parts)


def _write_launchers() -> None:
    LOCAL_BIN.mkdir(parents=True, exist_ok=True)
    python, root = _runtime()

    launcher = LOCAL_BIN / "fileconverter"
    launcher.write_text(f"""#!/bin/sh
# File Converter launcher — generated by `fileconverter --install`
export PATH="{_launcher_path_env()}:$PATH"
export PYTHONPATH="{root}:$PYTHONPATH"
exec "{python}" -m fileconverter "$@"
""")
    launcher.chmod(0o755)
    _print(f"  [OK] Launcher: {launcher}", "green")

    picker = LOCAL_BIN / "fileconverter-pick"
    picker.write_text(f"""#!/bin/sh
export PATH="{_launcher_path_env()}:$PATH"
export PYTHONPATH="{root}:$PYTHONPATH"
exec "{python}" -m fileconverter.ui.picker "$@"
""")
    picker.chmod(0o755)
    _print(f"  [OK] Picker: {picker}", "green")


def _save_binary_path() -> None:
    from fileconverter.config import CONFIG_DIR
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    (CONFIG_DIR / ".binary_path").write_text(str(LOCAL_BIN / "fileconverter"))
    (CONFIG_DIR / ".project_root").write_text(_runtime()[1])


# ── UTI mapping (GH #7: type-aware context menu) ──

# Documents need explicit UTIs; the media classes use the category UTIs that
# every registered audio/video/image type conforms to.
_DOC_UTIS = {
    "pdf": ["com.adobe.pdf"],
    "doc": ["com.microsoft.word.doc"],
    "docx": ["org.openxmlformats.wordprocessingml.document"],
    "xls": ["com.microsoft.excel.xls"],
    "xlsx": ["org.openxmlformats.spreadsheetml.sheet"],
    "ppt": ["com.microsoft.powerpoint.ppt"],
    "pptx": ["org.openxmlformats.presentationml.presentation"],
    "odt": ["org.oasis-open.opendocument.text"],
    "ods": ["org.oasis-open.opendocument.spreadsheet"],
    "odp": ["org.oasis-open.opendocument.presentation"],
    "rtf": ["public.rtf"],
    "txt": ["public.plain-text"],
    "csv": ["public.comma-separated-values-text"],
    "html": ["public.html"],
    "epub": ["org.idpf.epub-container"],
    "pages": ["com.apple.iwork.pages.sffpages", "com.apple.iwork.pages.pages"],
    "numbers": ["com.apple.iwork.numbers.sffnumbers", "com.apple.iwork.numbers.numbers"],
    "key": ["com.apple.iwork.keynote.sffkey", "com.apple.iwork.keynote.key"],
}


# ext → UTI as LaunchServices resolves it on THIS machine, filled by
# _resolve_system_utis(). Formats no installed app claims (e.g. mkv on a
# stock Mac) resolve to dynamic UTIs (dyn.*) that do NOT conform to
# public.movie/audio — without listing those explicitly, Finder would hide
# every preset on exactly those files.
_system_uti_cache: dict = {}


def _resolve_system_utis(extensions: set) -> dict:
    missing = sorted(e for e in extensions if e not in _system_uti_cache)
    if missing:
        try:
            with tempfile.TemporaryDirectory(prefix="fileconverter-uti-") as td:
                paths = []
                for ext in missing:
                    p = os.path.join(td, f"probe.{ext}")
                    open(p, "w").close()
                    paths.append(p)
                out = subprocess.run(
                    ["mdls", "-raw", "-name", "kMDItemContentType"] + paths,
                    capture_output=True, text=True, timeout=60,
                ).stdout
                values = out.split("\0")
                for ext, uti in zip(missing, values):
                    uti = uti.strip()
                    if uti and uti != "(null)":
                        _system_uti_cache[ext] = uti
        except (subprocess.SubprocessError, OSError):
            pass
    return _system_uti_cache


def _utis_for_preset(preset, system_utis: dict) -> list[str]:
    from fileconverter.helpers import (
        ANIMATED_IMAGE_EXTENSIONS, AUDIO_EXTENSIONS, IMAGE_EXTENSIONS,
        VIDEO_EXTENSIONS,
    )
    exts = {e.lower().lstrip(".") for e in preset.input_types}
    utis: set = set()
    # Category umbrellas: cover every registered type that conforms.
    if exts & VIDEO_EXTENSIONS:
        utis.add("public.movie")
    if exts & AUDIO_EXTENSIONS:
        utis.add("public.audio")
    if exts & IMAGE_EXTENSIONS:
        utis.add("public.image")
    if exts & ANIMATED_IMAGE_EXTENSIONS:
        utis.add("com.compuserve.gif")
    for ext in sorted(exts & set(_DOC_UTIS)):
        utis.update(_DOC_UTIS[ext])
    # Exact per-extension UTIs: catches the dyn.* ones the umbrellas miss.
    for ext in exts:
        uti = system_utis.get(ext)
        if uti:
            utis.add(uti)
    # A preset with no recognisable inputs still gets a menu entry on any file
    # rather than silently disappearing.
    return sorted(utis) or ["public.data"]


# ── Quick Action (.workflow) generation ──

def _workflow_info_plist(menu_item: str, send_types: list[str]) -> bytes:
    return plistlib.dumps({
        "NSServices": [{
            "NSBackgroundColorName": "background",
            "NSIconName": "NSActionTemplate",
            "NSMenuItem": {"default": menu_item},
            "NSMessage": "runWorkflowAsService",
            "NSRequiredContext": {},
            "NSSendFileTypes": send_types,
        }],
    })


def _workflow_document(command: str) -> bytes:
    """A one-action 'Run Shell Script' Quick Action, receiving files as $@."""
    return plistlib.dumps({
        "AMApplicationBuild": "528",
        "AMApplicationVersion": "2.10",
        "AMDocumentVersion": "2",
        "actions": [{
            "action": {
                "AMAccepts": {
                    "Container": "List", "Optional": True,
                    "Types": ["com.apple.cocoa.string"],
                },
                "AMActionVersion": "2.0.3",
                "AMApplication": ["Automator"],
                "AMParameterProperties": {
                    "COMMAND_STRING": {},
                    "CheckedForUserDefaultShell": {},
                    "inputMethod": {},
                    "shell": {},
                    "source": {},
                },
                "AMProvides": {
                    "Container": "List",
                    "Types": ["com.apple.cocoa.string"],
                },
                "ActionBundlePath": "/System/Library/Automator/Run Shell Script.action",
                "ActionName": "Run Shell Script",
                "ActionParameters": {
                    "COMMAND_STRING": command,
                    "CheckedForUserDefaultShell": True,
                    # 1 = pass input as arguments ($@) rather than stdin
                    "inputMethod": 1,
                    "shell": "/bin/zsh",
                    "source": "",
                },
                "BundleIdentifier": "com.apple.RunShellScript",
                "CFBundleVersion": "2.0.3",
                "CanShowSelectedItemsWhenRun": False,
                "CanShowWhenRun": True,
                "Category": ["AMCategoryUtilities"],
                "Class Name": "RunShellScriptAction",
                "InputUUID": str(uuid.uuid4()).upper(),
                "Keywords": ["Shell", "Script", "Command", "Run", "Unix"],
                "OutputUUID": str(uuid.uuid4()).upper(),
                "UUID": str(uuid.uuid4()).upper(),
                "UnlocalizedApplications": ["Automator"],
                "arguments": {
                    "0": {"default value": 0, "name": "inputMethod",
                          "required": "0", "type": 0, "uuid": "0"},
                    "1": {"default value": False, "name": "CheckedForUserDefaultShell",
                          "required": "0", "type": 0, "uuid": "1"},
                    "2": {"default value": "", "name": "source",
                          "required": "0", "type": 0, "uuid": "2"},
                    "3": {"default value": "", "name": "COMMAND_STRING",
                          "required": "0", "type": 0, "uuid": "3"},
                    "4": {"default value": "/bin/sh", "name": "shell",
                          "required": "0", "type": 0, "uuid": "4"},
                },
                "isViewVisible": 1,
                "location": "309.000000:253.000000",
                "nibPath": ("/System/Library/Automator/Run Shell Script.action"
                            "/Contents/Resources/Base.lproj/main.nib"),
            },
            "isViewVisible": 1,
        }],
        "connectors": {},
        "workflowMetaData": {
            "applicationBundleIDsByPath": {},
            "applicationPaths": [],
            "inputTypeIdentifier": "com.apple.Automator.fileSystemObject",
            "outputTypeIdentifier": "com.apple.Automator.nothing",
            "presentationMode": 15,
            "processesInput": 0,
            "serviceApplicationBundleID": "com.apple.finder",
            "serviceApplicationPath": "/System/Library/CoreServices/Finder.app",
            "serviceInputTypeIdentifier": "com.apple.Automator.fileSystemObject",
            "serviceOutputTypeIdentifier": "com.apple.Automator.nothing",
            "serviceProcessesInput": 0,
            "systemImageName": "NSActionTemplate",
            "useAutomaticInputType": 0,
            "workflowTypeIdentifier": "com.apple.Automator.servicesMenu",
        },
    })


def _write_workflow(bundle_name: str, menu_item: str, send_types: list[str],
                    command: str) -> None:
    bundle = SERVICES_DIR / bundle_name
    contents = bundle / "Contents"
    contents.mkdir(parents=True, exist_ok=True)
    (contents / "Info.plist").write_bytes(_workflow_info_plist(menu_item, send_types))
    (contents / "document.wflow").write_bytes(_workflow_document(command))


def _clean_workflows() -> list[str]:
    """Remove every File Converter workflow (stale presets included, GH #7)."""
    removed = []
    if SERVICES_DIR.exists():
        for wf in SERVICES_DIR.glob(WORKFLOW_GLOB):
            shutil.rmtree(wf, ignore_errors=True)
            removed.append(str(wf))
    return removed


def refresh_services(quiet: bool = False) -> int:
    """(Re)generate the Finder context-menu integration.

    Always writes menu.json (feeding the Finder Sync submenu) and the generic
    picker Quick Action. The per-preset Quick Actions are only generated when
    the submenu extension is NOT active — otherwise the menu would list
    everything twice. Called by --install and after every settings save, so
    the Finder menu never drifts out of sync with the config.
    """
    from fileconverter.config import load_settings
    settings = load_settings()

    _write_menu_json(settings)

    SERVICES_DIR.mkdir(parents=True, exist_ok=True)
    _clean_workflows()

    launcher = shlex.quote(str(LOCAL_BIN / "fileconverter"))
    picker = shlex.quote(str(LOCAL_BIN / "fileconverter-pick"))

    count = 0
    if not _extension_enabled():
        all_exts = set()
        for preset in settings.presets:
            all_exts.update(e.lower().lstrip(".") for e in preset.input_types)
        system_utis = _resolve_system_utis(all_exts)

        for preset in settings.presets:
            # Bundle names come from preset names; strip path separators.
            safe = preset.name.replace("/", " - ").replace(":", " ")
            command = (f"nohup {launcher} --conversion-preset "
                       f"{shlex.quote(preset.name)} \"$@\" >/dev/null 2>&1 &")
            _write_workflow(
                f"{WORKFLOW_PREFIX}{safe}.workflow",
                preset.short_name,
                _utis_for_preset(preset, system_utis),
                command,
            )
            count += 1

    # Generic entry: opens the preset picker with the full compatible list —
    # the macOS twin of the fileconverter-pick fallback on Linux.
    _write_workflow(
        PICKER_WORKFLOW_NAME,
        PICKER_MENU_ITEM,
        ["public.data"],
        f"nohup {picker} \"$@\" >/dev/null 2>&1 &",
    )
    count += 1

    _pbs_flush()
    if not quiet:
        if count == 1:
            _print("  [OK] Finder submenu active — created 1 Quick Action (picker)", "green")
        else:
            _print(f"  [OK] Created {count} Finder Quick Actions in {SERVICES_DIR}", "green")
    return count


def _pbs_flush() -> None:
    """Ask the pasteboard server to rescan ~/Library/Services."""
    pbs = "/System/Library/CoreServices/pbs"
    if os.path.exists(pbs):
        try:
            subprocess.run([pbs, "-flush"], capture_output=True, timeout=30)
            subprocess.run([pbs, "-update"], capture_output=True, timeout=30)
        except (subprocess.SubprocessError, OSError):
            pass


# ── Finder Sync extension (real context-menu submenu, like Linux) ──

def _write_menu_json(settings) -> None:
    """Preset list + translations for the Finder submenu. The extension
    re-reads this on every right-click, so edits apply instantly."""
    from fileconverter.i18n import _ as tr
    data = {
        "strings": {
            "menu_title": "File Converter",
            "configure": tr("Configure presets..."),
        },
        "presets": [{
            "name": p.name,
            "short": p.short_name,
            "extensions": sorted({e.lower().lstrip(".") for e in p.input_types}),
            "out": p.output_type.upper(),
        } for p in settings.presets],
    }
    APP_DIR.mkdir(parents=True, exist_ok=True)
    MENU_JSON.write_text(json.dumps(data, ensure_ascii=False, indent=1))


def _extension_enabled() -> bool:
    try:
        out = subprocess.run(["/usr/bin/pluginkit", "-m", "-i", EXT_BUNDLE_ID],
                             capture_output=True, text=True, timeout=15).stdout
    except (subprocess.SubprocessError, OSError):
        return False
    return any(line.strip().startswith("+") for line in out.splitlines())


def build_finder_extension(quiet: bool = False) -> str:
    """Build File Converter.app with the embedded Finder Sync extension.

    Returns "enabled" (submenu active), "built" (needs the System Settings
    toggle), or "unavailable" (no Swift toolchain / build failure — the
    UTI-scoped Quick Actions remain the context-menu integration).
    """
    swiftc = _find_swiftc()
    src_dir = Path(__file__).resolve().parent.parent / "ui" / "native"
    host_src = src_dir / "HostApp.swift"
    ext_src = src_dir / "FinderSyncExt.swift"
    if not swiftc or not host_src.exists() or not ext_src.exists():
        if not quiet:
            _print("  [NOTE] Swift toolchain not available — Finder submenu skipped,", "yellow")
            _print("         Quick Actions remain the context-menu integration.", "yellow")
        return "unavailable"

    app = HOST_APP
    macos_dir = app / "Contents" / "MacOS"
    ext = app / "Contents" / "PlugIns" / "FileConverterSync.appex"
    ext_macos = ext / "Contents" / "MacOS"
    shutil.rmtree(app, ignore_errors=True)
    macos_dir.mkdir(parents=True, exist_ok=True)
    ext_macos.mkdir(parents=True, exist_ok=True)

    # CFBundleSupportedPlatforms is not optional: LaunchServices records the
    # bundle without it, but pkd silently refuses to list the extension.
    common = {
        "CFBundleDevelopmentRegion": "en",
        "CFBundleInfoDictionaryVersion": "6.0",
        "CFBundleSupportedPlatforms": ["MacOSX"],
        "CFBundleShortVersionString": _app_version(),
        "CFBundleVersion": _app_version(),
        "LSMinimumSystemVersion": "13.0",
    }
    (app / "Contents" / "Info.plist").write_bytes(plistlib.dumps({
        **common,
        "CFBundleName": "File Converter",
        "CFBundleDisplayName": "File Converter",
        "CFBundleIdentifier": HOST_BUNDLE_ID,
        "CFBundleExecutable": "FileConverterHost",
        "CFBundlePackageType": "APPL",
        "LSUIElement": True,
        "NSHighResolutionCapable": True,
        "CFBundleURLTypes": [{
            "CFBundleURLName": HOST_BUNDLE_ID,
            "CFBundleURLSchemes": ["fileconverter"],
        }],
    }))
    (ext / "Contents" / "Info.plist").write_bytes(plistlib.dumps({
        **common,
        "CFBundleName": "FileConverterSync",
        "CFBundleDisplayName": "File Converter",
        "CFBundleIdentifier": EXT_BUNDLE_ID,
        "CFBundleExecutable": "FileConverterSync",
        "CFBundlePackageType": "XPC!",
        "NSExtension": {
            "NSExtensionPointIdentifier": "com.apple.FinderSync",
            "NSExtensionPrincipalClass": "FileConverterSync.FinderSync",
        },
    }))

    def _run(cmd: list) -> subprocess.CompletedProcess:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=600)

    steps = [
        [swiftc, "-O", "-parse-as-library", "-module-name", "FileConverterHost",
         str(host_src), "-o", str(macos_dir / "FileConverterHost")],
        [swiftc, "-O", "-parse-as-library", "-module-name", "FileConverterSync",
         str(ext_src), "-o", str(ext_macos / "FileConverterSync"),
         "-framework", "FinderSync",
         "-Xlinker", "-e", "-Xlinker", "_NSExtensionMain"],
    ]
    for cmd in steps:
        try:
            result = _run(cmd)
        except (subprocess.SubprocessError, OSError) as e:
            result = None
            err = str(e)
        if result is None or result.returncode != 0:
            if not quiet:
                tail = (result.stderr.strip().splitlines()[-3:] if result else [err])
                _print("  [WARN] Finder extension build failed — Quick Actions remain active", "yellow")
                for line in tail:
                    _print(f"         {line}", "yellow")
            shutil.rmtree(app, ignore_errors=True)
            return "unavailable"

    # Ad-hoc sign inside-out, then register and try to enable. pkd only
    # accepts sandboxed app extensions, so the appex gets the sandbox
    # entitlement plus a read-only exception for menu.json.
    entitlements = plistlib.dumps({
        "com.apple.security.app-sandbox": True,
        "com.apple.security.temporary-exception.files.home-relative-path.read-only":
            ["/.local/share/fileconverter/"],
    })
    with tempfile.NamedTemporaryFile("wb", suffix=".plist", delete=False) as f:
        f.write(entitlements)
        ent_path = f.name
    try:
        _run(["/usr/bin/codesign", "--force", "-s", "-",
              "--entitlements", ent_path, str(ext)])
        _run(["/usr/bin/codesign", "--force", "-s", "-", str(app)])
    finally:
        os.unlink(ent_path)
    lsregister = ("/System/Library/Frameworks/CoreServices.framework/Frameworks/"
                  "LaunchServices.framework/Support/lsregister")
    if os.path.exists(lsregister):
        _run([lsregister, "-f", str(app)])
    _run(["/usr/bin/pluginkit", "-a", str(ext)])
    _run(["/usr/bin/pluginkit", "-e", "use", "-i", EXT_BUNDLE_ID])

    if _extension_enabled():
        if not quiet:
            _print(f"  [OK] Finder submenu extension: {app}", "green")
        return "enabled"
    if not quiet:
        _print(f"  [OK] Built {app}", "green")
        _print("  [NOTE] Enable it under System Settings → General →", "yellow")
        _print("         Login Items & Extensions → Finder, then re-run setup.", "yellow")
    return "built"


# ── Native SwiftUI front-end ──

def _find_swiftc() -> str | None:
    """swiftc via the xcrun-backed /usr/bin shim — calling the binary inside
    CommandLineTools directly can't locate the SDK/standard library. Only use
    the shim when a developer directory is active, otherwise macOS pops the
    'install the Command Line Tools?' dialog instead of compiling."""
    try:
        probe = subprocess.run(["/usr/bin/xcode-select", "-p"],
                               capture_output=True, text=True, timeout=10)
        if probe.returncode != 0 or not probe.stdout.strip():
            return None
    except (subprocess.SubprocessError, OSError):
        return None
    if os.path.exists("/usr/bin/swiftc"):
        return "/usr/bin/swiftc"
    return shutil.which("swiftc")


def compile_native_ui(quiet: bool = False) -> bool:
    """Build the SwiftUI renderer (progress window / picker / settings).

    Failure is not fatal — the tkinter front-end takes over. Apple's bundled
    Tk 8.5 draws blank windows on recent macOS, so the native UI is strongly
    preferred whenever the Command Line Tools are present.
    """
    src = Path(__file__).resolve().parent.parent / "ui" / "native" / "FileConverterUI.swift"
    if not src.exists():
        if not quiet:
            _print("  [WARN] Native UI source missing — using tkinter fallback", "yellow")
        return False
    swiftc = _find_swiftc()
    if not swiftc:
        if not quiet:
            _print("  [NOTE] swiftc not found (xcode-select --install) — using tkinter UI", "yellow")
        return False

    BIN_DIR.mkdir(parents=True, exist_ok=True)
    try:
        result = subprocess.run(
            [swiftc, "-O", "-parse-as-library", str(src), "-o", str(UI_BIN)],
            capture_output=True, text=True, timeout=600,
        )
    except (subprocess.SubprocessError, OSError) as e:
        if not quiet:
            _print(f"  [WARN] Native UI build failed ({e}) — using tkinter fallback", "yellow")
        return False
    if result.returncode != 0:
        if not quiet:
            tail = (result.stderr or "").strip().splitlines()[-3:]
            _print("  [WARN] Native UI build failed — using tkinter fallback", "yellow")
            for line in tail:
                _print(f"         {line}", "yellow")
        return False
    UI_BIN.chmod(0o755)
    if not quiet:
        _print(f"  [OK] Native UI: {UI_BIN}", "green")
    return True


# ── Settings app bundle (macOS twin of the Linux .desktop entry) ──

def _install_settings_app() -> None:
    macos_dir = SETTINGS_APP / "Contents" / "MacOS"
    macos_dir.mkdir(parents=True, exist_ok=True)

    (SETTINGS_APP / "Contents" / "Info.plist").write_bytes(plistlib.dumps({
        "CFBundleName": "File Converter Settings",
        "CFBundleDisplayName": "File Converter Settings",
        "CFBundleIdentifier": "org.fileconverter.settings",
        "CFBundleExecutable": "fileconverter-settings",
        "CFBundlePackageType": "APPL",
        "CFBundleShortVersionString": _app_version(),
        "LSMinimumSystemVersion": "11.0",
        "NSHighResolutionCapable": True,
    }))

    script = macos_dir / "fileconverter-settings"
    script.write_text(f"""#!/bin/sh
exec "{LOCAL_BIN / 'fileconverter'}" --settings
""")
    script.chmod(0o755)
    _print(f"  [OK] Settings app: {SETTINGS_APP}", "green")


def _app_version() -> str:
    try:
        from fileconverter import __version__
        return __version__
    except Exception:
        return "0.0.0"


# ── Main flows ──

def is_installed() -> bool:
    from fileconverter.config import CONFIG_FILE
    has_config = CONFIG_FILE.exists()
    has_services = SERVICES_DIR.exists() and any(SERVICES_DIR.glob(WORKFLOW_GLOB))
    has_bin = (LOCAL_BIN / "fileconverter").exists()
    return has_config and (has_services or has_bin)


def run_install() -> None:
    _print("\n=== File Converter for macOS — Setup ===\n", "bold")

    _print("Checking dependencies:", "bold")
    check_dependencies()
    missing = _missing_required_formulae()
    if missing:
        _offer_brew_install(missing)
    if find_soffice() is None:
        _print("  [NOTE] LibreOffice is optional — only needed for document presets", "yellow")
        _print("         (To Pdf, To Docx, ...): brew install --cask libreoffice", "yellow")
    print()

    _print("Setting up configuration:", "bold")
    from fileconverter.config import ensure_config, CONFIG_FILE
    ensure_config()
    if CONFIG_FILE.exists():
        _print(f"  [OK] Config: {CONFIG_FILE}", "green")
    print()

    _print("Setting up command:", "bold")
    _write_launchers()
    _save_binary_path()
    local_bin = str(LOCAL_BIN)
    if local_bin not in os.environ.get("PATH", ""):
        _print(f"  [NOTE] Add {local_bin} to your PATH for terminal use:", "yellow")
        _print(f"    echo 'export PATH=\"$HOME/.local/bin:$PATH\"' >> ~/.zshrc", "yellow")
    print()

    _print("Building native UI (SwiftUI):", "bold")
    compile_native_ui()
    print()

    _print("Building Finder submenu (File Converter.app):", "bold")
    ext_state = build_finder_extension()
    print()

    _print("Setting up Finder context menu:", "bold")
    refresh_services()
    print()

    _print("Setting up app entry:", "bold")
    if ext_state == "unavailable":
        _install_settings_app()
    else:
        # File Converter.app doubles as the settings entry — drop the old
        # shell-script settings app from earlier versions.
        if SETTINGS_APP.exists():
            shutil.rmtree(SETTINGS_APP, ignore_errors=True)
        _print(f"  [OK] Settings: double-click {HOST_APP.name} (or fileconverter --settings)", "green")
    print()

    _print("=== Setup complete! ===\n", "bold")
    if ext_state == "enabled":
        _print("Right-click files in Finder → File Converter → choose a preset", "green")
        _print("(relaunch Finder once — killall Finder — if the submenu isn't there yet)", "green")
    else:
        _print("Right-click files in Finder → Quick Actions → choose a preset", "green")
        _print("(also under the Services submenu; first use may need a few seconds", "green")
        _print(" for Finder to index the new actions)", "green")
    _print("Or from terminal: fileconverter --conversion-preset 'To Mp4' file.avi\n", "green")


def run_uninstall() -> None:
    _print("\n=== File Converter — Uninstall ===\n", "bold")
    removed: list[str] = []

    removed += _clean_workflows()
    _pbs_flush()

    for name in ("fileconverter", "fileconverter-pick"):
        p = LOCAL_BIN / name
        if p.exists():
            p.unlink()
            removed.append(str(p))

    if SETTINGS_APP.exists():
        shutil.rmtree(SETTINGS_APP, ignore_errors=True)
        removed.append(str(SETTINGS_APP))

    if HOST_APP.exists():
        try:
            subprocess.run(["/usr/bin/pluginkit", "-e", "ignore", "-i", EXT_BUNDLE_ID],
                           capture_output=True, timeout=15)
        except (subprocess.SubprocessError, OSError):
            pass
        shutil.rmtree(HOST_APP, ignore_errors=True)
        removed.append(str(HOST_APP))

    from fileconverter.config import CONFIG_DIR
    if CONFIG_DIR.exists():
        shutil.rmtree(CONFIG_DIR, ignore_errors=True)
        removed.append(str(CONFIG_DIR))

    if APP_DIR.exists():
        shutil.rmtree(APP_DIR, ignore_errors=True)
        removed.append(str(APP_DIR))

    if removed:
        _print("Removed:", "bold")
        for r in removed:
            _print(f"  {r}", "green")
    else:
        _print("Nothing to remove — File Converter was not installed.", "yellow")
    _print("\nUninstall complete.\n", "bold")


def main() -> None:
    if "--uninstall" in sys.argv:
        run_uninstall()
    else:
        run_install()


if __name__ == "__main__":
    main()

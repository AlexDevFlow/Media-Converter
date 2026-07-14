"""Installer — distro-agnostic, auto-detects package manager and file managers."""

from __future__ import annotations
import os
import shutil
import subprocess
import sys
from pathlib import Path


# ── Output helpers ──

def _print(msg: str, color: str = "") -> None:
    colors = {"green": "\033[32m", "yellow": "\033[33m", "red": "\033[31m", "bold": "\033[1m", "cyan": "\033[36m"}
    reset = "\033[0m"
    prefix = colors.get(color, "")
    print(f"{prefix}{msg}{reset}")


# ── Package manager detection ──

def _detect_pkg_manager() -> tuple[str, str]:
    """Detect the system package manager. Returns (name, install_command_prefix)."""
    managers = [
        ("apt", "sudo apt install -y"),
        ("dnf", "sudo dnf install -y"),
        ("pacman", "sudo pacman -S --noconfirm"),
        ("zypper", "sudo zypper install -y"),
        ("apk", "sudo apk add"),
        ("xbps-install", "sudo xbps-install -y"),
        ("emerge", "sudo emerge"),
        ("nix-env", "nix-env -iA nixpkgs."),
    ]
    for name, cmd in managers:
        if shutil.which(name):
            return name, cmd
    return "unknown", ""


def _pkg_name(pkg_manager: str, generic: str) -> str:
    """Map a generic dependency name to the distro-specific package name."""
    pkg_map = {
        "ffmpeg": {
            "apt": "ffmpeg", "dnf": "ffmpeg-free", "pacman": "ffmpeg",
            "zypper": "ffmpeg", "apk": "ffmpeg", "xbps-install": "ffmpeg",
        },
        "imagemagick": {
            "apt": "imagemagick", "dnf": "ImageMagick", "pacman": "imagemagick",
            "zypper": "ImageMagick", "apk": "imagemagick", "xbps-install": "ImageMagick",
        },
        "ghostscript": {
            "apt": "ghostscript", "dnf": "ghostscript", "pacman": "ghostscript",
            "zypper": "ghostscript", "apk": "ghostscript", "xbps-install": "ghostscript",
        },
        "libreoffice": {
            "apt": "libreoffice", "dnf": "libreoffice-writer libreoffice-calc libreoffice-impress",
            "pacman": "libreoffice-still", "zypper": "libreoffice",
            "apk": "libreoffice", "xbps-install": "libreoffice",
        },
        "nautilus-python": {
            "apt": "python3-nautilus", "dnf": "nautilus-python",
            "pacman": "python-nautilus", "zypper": "python3-nautilus",
        },
    }
    return pkg_map.get(generic, {}).get(pkg_manager, generic)


def install_hint(generic: str) -> str:
    """Return a distro-appropriate install hint for a missing dependency."""
    mgr, cmd = _detect_pkg_manager()
    if mgr == "unknown":
        return f"Install {generic} using your system package manager."
    pkg = _pkg_name(mgr, generic)
    return f"Install it with: {cmd} {pkg}"


# ── Dependency checking ──

def _check_dependency(name: str, commands: list[str], install_cmd: str) -> bool:
    """Check if any of the given commands exist in PATH."""
    for cmd in commands:
        if shutil.which(cmd):
            _print(f"  [OK] {name}", "green")
            return True
    _print(f"  [MISSING] {name} — install with: {install_cmd}", "yellow")
    return False


def check_dependencies() -> dict[str, bool]:
    """Check all required and optional dependencies. Returns status dict."""
    pkg_mgr, install_prefix = _detect_pkg_manager()

    results = {}
    deps = [
        ("FFmpeg", ["ffmpeg"], "ffmpeg"),
        ("ImageMagick", ["magick", "convert", "convert-im6", "convert-im6.q16"], "imagemagick"),
        ("Ghostscript", ["gs"], "ghostscript"),
        ("LibreOffice", ["libreoffice", "soffice"], "libreoffice"),
    ]

    for label, commands, generic in deps:
        pkg = _pkg_name(pkg_mgr, generic)
        hint = f"{install_prefix} {pkg}" if install_prefix else f"Install {generic} using your package manager"
        results[label] = _check_dependency(label, commands, hint)

    return results


def get_missing_install_command() -> str | None:
    """Return a single command to install all missing dependencies, or None if all present."""
    pkg_mgr, install_prefix = _detect_pkg_manager()
    if not install_prefix:
        return None

    missing = []
    checks = [
        (["ffmpeg"], "ffmpeg"),
        (["magick", "convert", "convert-im6"], "imagemagick"),
        (["gs"], "ghostscript"),
        (["libreoffice", "soffice"], "libreoffice"),
    ]
    for commands, generic in checks:
        if not any(shutil.which(c) for c in commands):
            missing.append(_pkg_name(pkg_mgr, generic))

    if not missing:
        return None
    return f"{install_prefix} {' '.join(missing)}"


# ── Nautilus extension ──

def _get_nautilus_ext_source() -> str:
    """Get the Nautilus extension source code.

    When running from PyInstaller bundle, the file may be in a temp dir.
    When running from source, it's next to this file.
    """
    # Try next to this file first (source install)
    source = Path(__file__).parent / "nautilus_extension.py"
    if source.exists():
        return source.read_text()

    # PyInstaller: check _MEIPASS
    meipass = getattr(sys, '_MEIPASS', None)
    if meipass:
        bundled = Path(meipass) / "fileconverter" / "integration" / "nautilus_extension.py"
        if bundled.exists():
            return bundled.read_text()

    return ""


def _install_nautilus_extension() -> bool:
    """Install the Nautilus python extension."""
    ext_dirs = [
        Path.home() / ".local" / "share" / "nautilus-python" / "extensions",
        Path.home() / ".local" / "share" / "nautilus" / "python-extensions",
    ]

    source_code = _get_nautilus_ext_source()
    if not source_code:
        _print("  [ERROR] Could not find nautilus_extension.py", "red")
        return False

    for ext_dir in ext_dirs:
        ext_dir.mkdir(parents=True, exist_ok=True)
        dest = ext_dir / "fileconverter_nautilus.py"
        try:
            dest.write_text(source_code)
            _print(f"  [OK] Nautilus extension → {dest}", "green")
            return True
        except OSError as e:
            _print(f"  [WARN] Could not write to {dest}: {e}", "yellow")

    return False


# ── Binary / launcher setup ──

def _find_self() -> str:
    """Find the path to the fileconverter executable (PyInstaller binary or source)."""
    # PyInstaller frozen binary
    if getattr(sys, 'frozen', False):
        return sys.executable

    # Installed via pip or in ~/.local/bin
    fc = shutil.which("fileconverter")
    if fc:
        return fc

    return ""


def _save_binary_path() -> None:
    """Save the binary/launcher path so the Nautilus extension can find it."""
    from fileconverter.config import CONFIG_DIR
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    binary = _find_self()
    if binary:
        (CONFIG_DIR / ".binary_path").write_text(binary)
        _print(f"  [OK] Binary path saved: {binary}", "green")

    # Also save project root for source installs
    if not getattr(sys, 'frozen', False):
        project_root = str(Path(__file__).parent.parent.parent.resolve())
        (CONFIG_DIR / ".project_root").write_text(project_root)


def _create_launcher_script() -> bool:
    """Create a shell wrapper in ~/.local/bin/ (only for source installs, not PyInstaller)."""
    if getattr(sys, 'frozen', False):
        # For PyInstaller, symlink the binary instead
        local_bin = Path.home() / ".local" / "bin"
        local_bin.mkdir(parents=True, exist_ok=True)
        link = local_bin / "fileconverter"
        target = Path(sys.executable)

        if link.exists() or link.is_symlink():
            link.unlink()
        try:
            link.symlink_to(target)
            _print(f"  [OK] Symlink: {link} → {target}", "green")
        except OSError:
            # Symlink failed (cross-device?), copy instead
            shutil.copy2(target, link)
            link.chmod(0o755)
            _print(f"  [OK] Copied binary to {link}", "green")

        # The frozen build is a single binary, so the picker lives behind
        # --pick. Thunar/PCManFM custom actions (and run_install's own
        # instructions) call `fileconverter-pick`, so it must exist.
        picker = local_bin / "fileconverter-pick"
        if picker.exists() or picker.is_symlink():
            picker.unlink()
        picker.write_text(f"""#!/bin/sh
exec "{link}" --pick "$@"
""")
        picker.chmod(0o755)
        _print(f"  [OK] Picker: {picker}", "green")
        return True

    # Source install: create wrapper scripts
    local_bin = Path.home() / ".local" / "bin"
    local_bin.mkdir(parents=True, exist_ok=True)

    project_root = str(Path(__file__).parent.parent.parent.resolve())
    python = sys.executable or "/usr/bin/python3"

    launcher = local_bin / "fileconverter"
    launcher.write_text(f"""#!/bin/sh
export PYTHONPATH="{project_root}:$PYTHONPATH"
exec {python} -m fileconverter "$@"
""")
    launcher.chmod(0o755)
    _print(f"  [OK] Launcher: {launcher}", "green")

    picker = local_bin / "fileconverter-pick"
    # fileconverter.ui.picker (not preset_picker) — it falls back to tkinter
    # when GTK is missing, instead of crashing (GH #5).
    picker.write_text(f"""#!/bin/sh
export PYTHONPATH="{project_root}:$PYTHONPATH"
exec {python} -m fileconverter.ui.picker "$@"
""")
    picker.chmod(0o755)
    _print(f"  [OK] Picker: {picker}", "green")

    return True


# ── Nemo actions ──

def _install_nemo_actions() -> bool:
    nemo_dir = Path.home() / ".local" / "share" / "nemo" / "actions"
    nemo_dir.mkdir(parents=True, exist_ok=True)

    try:
        from fileconverter.config import load_settings
        settings = load_settings()
    except Exception as e:
        _print(f"  [ERROR] Could not load settings: {e}", "red")
        return False

    fc = _find_self() or shutil.which("fileconverter") or "fileconverter"

    for f in nemo_dir.glob("fileconverter-*.nemo_action"):
        f.unlink()

    count = 0
    for preset in settings.presets:
        safe_name = preset.name.replace("/", "-").replace(" ", "_").lower()
        action_file = nemo_dir / f"fileconverter-{safe_name}.nemo_action"
        mimetypes = ";".join(ext for ext in preset.input_types)
        action_file.write_text(f"""[Nemo Action]
Name=File Converter: {preset.short_name}
Comment=Convert to {preset.output_type.upper()}
Exec={fc} --conversion-preset "{preset.name}" %F
Selection=Any
Extensions={mimetypes};
""")
        count += 1

    _print(f"  [OK] Created {count} Nemo actions", "green")
    return True


# ── Dolphin service menu ──

def _dolphin_service_dirs() -> list[Path]:
    """Both locations — for cleaning and for detection, never both for writing."""
    return [
        Path.home() / ".local" / "share" / "kio" / "servicemenus",
        Path.home() / ".local" / "share" / "kservices5" / "ServiceMenus",
    ]


def _dolphin_target_dir() -> Path:
    """The ONE directory to write service menus into.

    KIO ≥ 5.85 (Plasma 5.22+/6) scans both `kio/servicemenus` and the legacy
    `kservices5/ServiceMenus`, so writing to both would show every action
    twice. Older KIO scans only the legacy dir. Detect which world we're in
    from the system-wide directories, defaulting to the modern one.
    """
    modern = Path.home() / ".local" / "share" / "kio" / "servicemenus"
    legacy = Path.home() / ".local" / "share" / "kservices5" / "ServiceMenus"

    system_modern = any(
        Path(p).is_dir() for p in
        ("/usr/share/kio/servicemenus", "/usr/local/share/kio/servicemenus")
    )
    system_legacy = any(
        Path(p).is_dir() for p in
        ("/usr/share/kservices5/ServiceMenus", "/usr/local/share/kservices5/ServiceMenus")
    )
    if system_legacy and not system_modern:
        return legacy
    return modern


def _clean_dolphin_service_menus() -> list[str]:
    """Remove every service menu we ever generated — the old monolithic
    fileconverter.desktop included, plus any stale per-type group from a
    previous preset set (GH #7)."""
    removed = []
    for service_dir in _dolphin_service_dirs():
        if not service_dir.exists():
            continue
        for f in service_dir.glob("fileconverter*.desktop"):
            try:
                f.unlink()
                removed.append(str(f))
            except OSError:
                pass
    return removed


def _install_dolphin_service_menu() -> bool:
    """Generate KDE service menus, one .desktop per group of presets sharing
    the same input types (GH #7).

    Dolphin filters a service menu by its MimeType= line, but has no
    per-action filter — a single file listing every preset therefore offers
    "To Jpg" on an mkv. Grouping presets by their input_types set and giving
    each group its own MimeType makes the menu type-aware. Every group keeps
    the same X-KDE-Submenu, and KIO merges same-named submenus, so the user
    still sees a single "File Converter" menu.
    """
    from fileconverter.helpers import mime_types_for_extensions

    try:
        from fileconverter.config import load_settings
        settings = load_settings()
    except Exception as e:
        _print(f"  [ERROR] Could not load settings: {e}", "red")
        return False

    fc = _find_self() or shutil.which("fileconverter") or "fileconverter"

    # Group presets by the set of extensions they accept — presets with
    # identical inputs share one .desktop (and therefore one MimeType line).
    groups: dict[frozenset, list] = {}
    for preset in settings.presets:
        key = frozenset(e.lower().lstrip(".") for e in preset.input_types)
        if not key:
            continue
        groups.setdefault(key, []).append(preset)

    _clean_dolphin_service_menus()

    service_dir = _dolphin_target_dir()
    service_dir.mkdir(parents=True, exist_ok=True)

    written = 0
    for idx, (exts, presets) in enumerate(sorted(
            groups.items(), key=lambda kv: sorted(kv[0]))):
        mimes = mime_types_for_extensions(exts)
        if not mimes:
            continue

        actions = ";".join(f"action{i}" for i in range(len(presets)))
        lines = [
            "[Desktop Entry]",
            "Type=Service",
            "ServiceTypes=KonqPopupMenu/Plugin",
            f"MimeType={';'.join(mimes)};",
            "X-KDE-Submenu=File Converter",
            f"Actions={actions}",
            "",
        ]
        for i, preset in enumerate(presets):
            lines += [
                f"[Desktop Action action{i}]",
                f"Name={preset.short_name}",
                f'Exec="{fc}" --conversion-preset "{preset.name}" %F',
                "",
            ]

        desktop_file = service_dir / f"fileconverter-group{idx}.desktop"
        desktop_file.write_text("\n".join(lines))
        desktop_file.chmod(0o755)
        written += 1

    if not written:
        _print("  [WARN] No preset had a recognisable input type — no menu written",
               "yellow")
        return False

    _print(f"  [OK] Dolphin service menus: {written} type groups → {service_dir}",
           "green")
    return True


# ── Desktop entry ──

def refresh_menus(quiet: bool = True) -> None:
    """Regenerate the file-manager menus from the current presets.

    Called after the settings window saves. Without this, adding, renaming or
    deleting a preset leaves the Nemo actions and the Dolphin service menus
    (which encode whole preset groups) stale until the user re-runs --install.
    Only touches integrations that are already installed.
    """
    import contextlib
    import io

    sink = io.StringIO()
    with contextlib.redirect_stdout(sink) if quiet else contextlib.nullcontext():
        nemo_dir = Path.home() / ".local" / "share" / "nemo" / "actions"
        if nemo_dir.exists() and any(nemo_dir.glob("fileconverter-*.nemo_action")):
            _install_nemo_actions()

        if any(d.exists() and any(d.glob("fileconverter*.desktop"))
               for d in _dolphin_service_dirs()):
            _install_dolphin_service_menu()


def _install_desktop_entry() -> None:
    desktop_dir = Path.home() / ".local" / "share" / "applications"
    desktop_dir.mkdir(parents=True, exist_ok=True)

    fc = _find_self() or shutil.which("fileconverter") or "fileconverter"

    dest = desktop_dir / "fileconverter-settings.desktop"
    dest.write_text(f"""[Desktop Entry]
Type=Application
Name=File Converter Settings
Comment=Configure File Converter conversion presets
Exec={fc} --settings
Icon=preferences-system
Categories=Utility;Settings;
Terminal=false
""")
    _print(f"  [OK] Desktop entry installed", "green")


# ── Config ──

def _ensure_config() -> None:
    from fileconverter.config import ensure_config, CONFIG_FILE
    ensure_config()
    if CONFIG_FILE.exists():
        _print(f"  [OK] Config: {CONFIG_FILE}", "green")
    else:
        _print(f"  [WARN] Config not created at {CONFIG_FILE}", "yellow")


# ── Nautilus-python availability ──

def _has_nautilus_python() -> bool:
    try:
        import gi
        gi.require_version("Nautilus", "4.0")
        return True
    except (ImportError, ValueError):
        pass
    try:
        import gi
        gi.require_version("Nautilus", "3.0")
        return True
    except (ImportError, ValueError):
        return False


# ── Main install flow ──

def is_installed() -> bool:
    """Check if File Converter context menu integration is set up."""
    from fileconverter.config import CONFIG_FILE
    integration_files = [
        # Nautilus
        Path.home() / ".local" / "share" / "nautilus-python" / "extensions" / "fileconverter_nautilus.py",
        Path.home() / ".local" / "share" / "nautilus" / "python-extensions" / "fileconverter_nautilus.py",
    ]
    # Nemo generates one action file per preset, Dolphin one .desktop per
    # input-type group — both are globs, and must match what install and
    # uninstall use (GH #7).
    nemo_dir = Path.home() / ".local" / "share" / "nemo" / "actions"
    has_nemo = nemo_dir.exists() and any(nemo_dir.glob("fileconverter-*.nemo_action"))
    has_dolphin = any(
        d.exists() and any(d.glob("fileconverter*.desktop"))
        for d in _dolphin_service_dirs()
    )

    has_config = CONFIG_FILE.exists()
    has_integration = has_nemo or has_dolphin or any(f.exists() for f in integration_files)
    has_bin = shutil.which("fileconverter") is not None
    return has_config and (has_integration or has_bin)


def run_install() -> None:
    """Full installation flow."""
    _print("\n=== File Converter for Linux — Setup ===\n", "bold")

    # Step 1: Dependencies
    _print("Checking dependencies:", "bold")
    dep_status = check_dependencies()
    pkg_mgr, install_prefix = _detect_pkg_manager()

    # Check nautilus-python
    if shutil.which("nautilus"):
        if _has_nautilus_python():
            _print("  [OK] Nautilus Python extension support", "green")
        else:
            pkg = _pkg_name(pkg_mgr, "nautilus-python")
            hint = f"{install_prefix} {pkg}" if install_prefix else "Install nautilus-python"
            _print(f"  [MISSING] Nautilus Python bindings — {hint}", "yellow")

    missing_cmd = get_missing_install_command()
    if missing_cmd:
        _print(f"\n  Install missing dependencies:\n  {missing_cmd}\n", "cyan")

    # Warn Fedora users about ffmpeg-free lacking H.264/H.265 encoders
    if pkg_mgr == "dnf":
        _print("  [NOTE] Fedora's ffmpeg-free package lacks H.264/H.265 encoders.", "yellow")
        _print("         Video presets (To Mp4, To Mkv) need the full ffmpeg from RPM Fusion:", "yellow")
        _print("         https://rpmfusion.org/Configuration", "yellow")
        _print("         sudo dnf install ffmpeg --allowerasing", "yellow")
    print()

    # Step 2: Config
    _print("Setting up configuration:", "bold")
    _ensure_config()
    print()

    # Step 3: Launcher / binary
    _print("Setting up command:", "bold")
    _create_launcher_script()
    _save_binary_path()

    # Check PATH
    local_bin = str(Path.home() / ".local" / "bin")
    if local_bin not in os.environ.get("PATH", ""):
        _print(f"  [NOTE] Add {local_bin} to your PATH if not already:", "yellow")
        _print(f"    echo 'export PATH=\"$HOME/.local/bin:$PATH\"' >> ~/.bashrc", "yellow")
    print()

    # Step 4: File manager integration
    _print("Setting up context menu:", "bold")

    nautilus_ok = False
    if shutil.which("nautilus"):
        _print("  Detected: Nautilus (GNOME/Ubuntu)", "bold")
        if _has_nautilus_python():
            nautilus_ok = _install_nautilus_extension()
        else:
            _print("  Skipped (install nautilus-python first, then re-run setup)", "yellow")

    if shutil.which("nemo"):
        _print("  Detected: Nemo (Cinnamon/Mint)", "bold")
        _install_nemo_actions()

    if shutil.which("dolphin"):
        _print("  Detected: Dolphin (KDE)", "bold")
        _install_dolphin_service_menu()

    if shutil.which("thunar"):
        _print("  Detected: Thunar (XFCE)", "bold")
        _print("  Add a custom action: fileconverter-pick %F", "green")

    if shutil.which("pcmanfm") or shutil.which("pcmanfm-qt"):
        _print("  Detected: PCManFM (LXDE/LXQt)", "bold")
        _print("  Use from terminal: fileconverter-pick <files>", "green")
    print()

    # Step 5: Desktop entry
    _print("Setting up app entry:", "bold")
    _install_desktop_entry()
    print()

    # Done
    _print("=== Setup complete! ===\n", "bold")
    if nautilus_ok:
        _print("Restart your file manager to activate:", "bold")
        _print("  nautilus -q", "cyan")
        print()
    _print("Right-click files → File Converter → choose a preset", "green")
    _print("Or from terminal: fileconverter --conversion-preset 'To Mp4' file.avi\n", "green")


# ── Uninstall ──

def run_uninstall() -> None:
    """Remove all File Converter integration files."""
    _print("\n=== File Converter — Uninstall ===\n", "bold")

    removed = []

    # Nautilus extension
    for d in [
        Path.home() / ".local" / "share" / "nautilus-python" / "extensions" / "fileconverter_nautilus.py",
        Path.home() / ".local" / "share" / "nautilus" / "python-extensions" / "fileconverter_nautilus.py",
    ]:
        if d.exists():
            d.unlink()
            removed.append(str(d))

    # Nemo actions
    nemo_dir = Path.home() / ".local" / "share" / "nemo" / "actions"
    if nemo_dir.exists():
        for f in nemo_dir.glob("fileconverter-*.nemo_action"):
            f.unlink()
            removed.append(str(f))

    # Dolphin service menus (glob: the monolithic file from older versions
    # and every per-type group — GH #7)
    removed += _clean_dolphin_service_menus()

    # Desktop entry
    desktop = Path.home() / ".local" / "share" / "applications" / "fileconverter-settings.desktop"
    if desktop.exists():
        desktop.unlink()
        removed.append(str(desktop))

    # Launcher scripts (only remove if they point to us)
    for name in ["fileconverter", "fileconverter-pick"]:
        p = Path.home() / ".local" / "bin" / name
        if p.exists():
            p.unlink()
            removed.append(str(p))

    # Config directory
    from fileconverter.config import CONFIG_DIR
    if CONFIG_DIR.exists():
        shutil.rmtree(CONFIG_DIR)
        removed.append(str(CONFIG_DIR))

    if removed:
        _print("Removed:", "bold")
        for r in removed:
            _print(f"  {r}", "green")
    else:
        _print("Nothing to remove — File Converter was not installed.", "yellow")

    _print("\nUninstall complete. Restart your file manager.\n", "bold")


def main() -> None:
    if "--uninstall" in sys.argv:
        run_uninstall()
    else:
        run_install()


if __name__ == "__main__":
    main()

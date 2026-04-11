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
    picker.write_text(f"""#!/bin/sh
export PYTHONPATH="{project_root}:$PYTHONPATH"
exec {python} -m fileconverter.ui.preset_picker "$@"
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

def _install_dolphin_service_menu() -> bool:
    service_dirs = [
        Path.home() / ".local" / "share" / "kio" / "servicemenus",
        Path.home() / ".local" / "share" / "kservices5" / "ServiceMenus",
    ]

    try:
        from fileconverter.config import load_settings
        settings = load_settings()
    except Exception as e:
        _print(f"  [ERROR] Could not load settings: {e}", "red")
        return False

    fc = _find_self() or shutil.which("fileconverter") or "fileconverter"

    for service_dir in service_dirs:
        service_dir.mkdir(parents=True, exist_ok=True)
        desktop_file = service_dir / "fileconverter.desktop"

        actions = ";".join(f"action{i}" for i in range(len(settings.presets)))
        lines = [
            "[Desktop Entry]",
            "Type=Service",
            "ServiceTypes=KonqPopupMenu/Plugin",
            "MimeType=application/octet-stream;",
            "X-KDE-Submenu=File Converter",
            f"Actions={actions}",
            "",
        ]
        for i, preset in enumerate(settings.presets):
            lines += [
                f"[Desktop Action action{i}]",
                f"Name={preset.short_name}",
                f'Exec={fc} --conversion-preset "{preset.name}" %F',
                "",
            ]

        desktop_file.write_text("\n".join(lines))
        _print(f"  [OK] Dolphin service menu installed", "green")
        return True

    return False


# ── Desktop entry ──

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
        # Dolphin
        Path.home() / ".local" / "share" / "kio" / "servicemenus" / "fileconverter.desktop",
        Path.home() / ".local" / "share" / "kservices5" / "ServiceMenus" / "fileconverter.desktop",
    ]
    # Nemo generates one action file per preset — check if any exist
    nemo_dir = Path.home() / ".local" / "share" / "nemo" / "actions"
    has_nemo = nemo_dir.exists() and any(nemo_dir.glob("fileconverter-*.nemo_action"))

    has_config = CONFIG_FILE.exists()
    has_integration = has_nemo or any(f.exists() for f in integration_files)
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

    # Dolphin service menus
    for d in [
        Path.home() / ".local" / "share" / "kio" / "servicemenus" / "fileconverter.desktop",
        Path.home() / ".local" / "share" / "kservices5" / "ServiceMenus" / "fileconverter.desktop",
    ]:
        if d.exists():
            d.unlink()
            removed.append(str(d))

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

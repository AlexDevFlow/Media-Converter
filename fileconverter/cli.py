"""CLI entry point — mirrors the original's interface plus --install/--uninstall for Linux."""

from __future__ import annotations
import argparse
import os
import sys
import threading
from concurrent.futures import ThreadPoolExecutor

from fileconverter import __version__
from fileconverter.config import load_settings
from fileconverter import i18n
from fileconverter.i18n import _
from fileconverter.jobs.base import ConversionJob, ConversionState
from fileconverter.jobs.factory import create_job


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="fileconverter",
        description="File Converter for Linux — convert files from the command line or context menu.",
    )
    p.add_argument("--version", action="version", version=f"fileconverter {__version__}")
    p.add_argument("--conversion-preset", dest="preset_name",
                    help="Name of the conversion preset to use")
    p.add_argument("--input-files", dest="input_files_list",
                    help="Path to a text file containing input file paths (one per line)")
    p.add_argument("--settings", action="store_true",
                    help="Open the settings window")
    p.add_argument("--install", action="store_true",
                    help="Set up context menu integration and dependencies")
    p.add_argument("--uninstall", action="store_true",
                    help="Remove all File Converter integration files")
    p.add_argument("--verbose", action="store_true",
                    help="Show verbose output")
    p.add_argument("files", nargs="*", help="Input files to convert")
    return p.parse_args()


def _collect_files(args: argparse.Namespace) -> list[str]:
    """Gather input files from arguments and/or --input-files list."""
    files = list(args.files)
    if args.input_files_list:
        try:
            with open(args.input_files_list, "r") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        files.append(line)
        except OSError as e:
            print(_("Error reading input file list: {error}").format(error=e), file=sys.stderr)
            sys.exit(1)
    return [os.path.abspath(f) for f in files]


def _run_headless(jobs: list[ConversionJob], max_workers: int) -> None:
    """Run conversions without GUI (fallback if GTK unavailable)."""
    def _worker(job: ConversionJob) -> None:
        try:
            job.prepare()
            job.run()
        except Exception as e:
            job.error_message = str(e)
            job.state = ConversionState.FAILED

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = [pool.submit(_worker, j) for j in jobs]
        for f in futures:
            f.result()

    failed = [j for j in jobs if j.state == ConversionState.FAILED]
    if failed:
        for j in failed:
            print(_("FAILED: {name} — {error}").format(
                name=j.input_filename, error=j.error_message), file=sys.stderr)
        sys.exit(1)
    else:
        for j in jobs:
            print(_("Done: {name} → {path}").format(
                name=j.input_filename, path=j.output_path))


def _apply_language_from_settings() -> None:
    """Apply the saved UI language as early as possible."""
    try:
        s = load_settings()
        i18n.init(s.language)
    except Exception:
        pass


def main() -> None:
    _apply_language_from_settings()
    args = _parse_args()

    # --install
    if args.install:
        from fileconverter.integration.install import run_install
        run_install()
        return

    # --uninstall
    if args.uninstall:
        from fileconverter.integration.install import run_uninstall
        run_uninstall()
        return

    # --settings
    if args.settings:
        try:
            from fileconverter.ui.settings_window import run_settings
            run_settings()
        except (ImportError, ValueError):
            print(_("GTK 4 is required for the settings window."), file=sys.stderr)
            sys.exit(1)
        return

    # No arguments at all → first-run check, then show help or run install
    if not args.preset_name and not args.files:
        from fileconverter.integration.install import is_installed
        if not is_installed():
            print(_("File Converter is not set up yet. Running setup..."))
            print()
            from fileconverter.integration.install import run_install
            run_install()
            return
        else:
            print(f"File Converter {__version__}")
            print()
            print(_("Usage:"))
            print("  fileconverter --conversion-preset 'To Mp4' file.avi  " + _("Convert files"))
            print("  fileconverter --settings                             " + _("Open settings"))
            print("  fileconverter --install                              " + _("Re-run setup"))
            print("  fileconverter --uninstall                            " + _("Remove integration"))
            print()
            print(_("Or right-click files in your file manager!"))
            return

    if not args.preset_name:
        print(_("Error: --conversion-preset is required."), file=sys.stderr)
        print("Usage: fileconverter --conversion-preset 'To Mp4' file1.avi file2.mkv", file=sys.stderr)
        sys.exit(1)

    files = _collect_files(args)
    if not files:
        print(_("Error: no input files specified."), file=sys.stderr)
        sys.exit(1)

    for f in files:
        if not os.path.exists(f):
            print(_("Error: file not found: {path}").format(path=f), file=sys.stderr)
            sys.exit(1)

    settings = load_settings()
    preset = None
    for p in settings.presets:
        if p.name == args.preset_name:
            preset = p
            break

    if preset is None:
        print(_("Error: preset '{name}' not found.").format(name=args.preset_name), file=sys.stderr)
        print(_("Available presets:"), file=sys.stderr)
        for p in settings.presets:
            print(f"  - {p.name}", file=sys.stderr)
        sys.exit(1)

    # Resolve hardware acceleration
    from fileconverter.jobs.ffmpeg import resolve_hwaccel
    hw_accel = resolve_hwaccel(settings.hardware_acceleration)
    if args.verbose and hw_accel != "off":
        print(_("Hardware acceleration: {mode}").format(mode=hw_accel), file=sys.stderr)

    jobs = [create_job(preset, f, hw_accel=hw_accel) for f in files]

    try:
        from fileconverter.ui.progress_window import run_with_progress
        run_with_progress(jobs, settings)
    except (ImportError, ValueError):
        if args.verbose:
            print(_("GTK not available, running headless."), file=sys.stderr)
        _run_headless(jobs, settings.max_simultaneous_conversions)


if __name__ == "__main__":
    main()

"""CLI entry point — mirrors the original's interface plus --install/--uninstall."""

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
from fileconverter.jobs.base import ConversionJob, ConversionState, prepare_all
from fileconverter.jobs.factory import create_job


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="fileconverter",
        description="File Converter for Linux and macOS — convert files from the command line or context menu.",
    )
    p.add_argument("--version", action="version", version=f"fileconverter {__version__}")
    p.add_argument("--conversion-preset", dest="preset_name",
                    help="Name of the conversion preset to use")
    p.add_argument("--input-files", dest="input_files_list",
                    help="Path to a text file containing input file paths (one per line)")
    p.add_argument("--settings", action="store_true",
                    help="Open the settings window")
    p.add_argument("--pick", action="store_true",
                    help="Open the preset picker for the given files")
    p.add_argument("--install", action="store_true",
                    help="Set up context menu integration and dependencies")
    p.add_argument("--uninstall", action="store_true",
                    help="Remove all File Converter integration files")
    p.add_argument("--verbose", action="store_true",
                    help="Show verbose output")
    p.add_argument("--self-check", dest="self_check", action="store_true",
                    help="Verify the bundled presets load, then exit (diagnostic)")
    p.add_argument("files", nargs="*", help="Input files to convert")
    return p.parse_args()


# Presets that must be present for a build to be considered correctly bundled.
_REQUIRED_PRESETS = {
    "To Mp4", "To Mp3", "To Png", "To Pdf",
    "To Mp4 (H.265)", "To Mp4 (AV1)", "To Mov (ProRes)",
    "To Aiff", "To Wma", "To Ac3", "To M4a (Apple Lossless)",
    "To Jp2", "To Tga", "To Epub", "To Rtf", "To Txt", "To Html", "To Csv",
}


def _self_check() -> None:
    """Load settings (which loads the bundled default presets) and confirm the
    expected presets are present. Exits non-zero on a bundling regression.

    Deliberately avoids GTK and ffmpeg so it runs in a headless CI runner."""
    settings = load_settings()
    names = {p.name for p in settings.presets}
    missing = sorted(_REQUIRED_PRESETS - names)
    print(f"fileconverter {__version__}: {len(settings.presets)} presets loaded")
    if missing:
        print(f"self-check FAILED — missing presets: {missing}", file=sys.stderr)
        sys.exit(1)
    print("self-check OK")


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
    """Run conversions without GUI (fallback when no toolkit is available)."""
    def _worker(job: ConversionJob) -> None:
        try:
            if job.state != ConversionState.FAILED:   # prepare() may have failed
                job.run()
        except Exception as e:
            job.error_message = str(e)
            job.state = ConversionState.FAILED

    # Claim every output path before any conversion starts (see prepare_all).
    prepare_all(jobs)

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = [pool.submit(_worker, j) for j in jobs]
        for f in futures:
            f.result()

    failed = [j for j in jobs if j.state == ConversionState.FAILED]
    _notify_headless_result(jobs, failed)
    if failed:
        for j in failed:
            print(_("FAILED: {name} — {error}").format(
                name=j.input_filename, error=j.error_message), file=sys.stderr)
        sys.exit(1)
    else:
        for j in jobs:
            print(_("Done: {name} → {path}").format(
                name=j.input_filename, path=j.output_path))


def _notify_headless_result(jobs: list[ConversionJob], failed: list[ConversionJob]) -> None:
    """Desktop notification when launched without a terminal (e.g. from the
    file manager with no GUI toolkit) — otherwise the user gets no feedback."""
    if sys.stdout.isatty():
        return
    try:
        from fileconverter.ui import notify
        if failed:
            notify("File Converter",
                   _("{done}/{total} completed, {failed} failed").format(
                       done=len(jobs) - len(failed), total=len(jobs),
                       failed=len(failed)))
        else:
            done = len(jobs)
            if done == 1:
                notify("File Converter", _("Done: {name} → {path}").format(
                    name=jobs[0].input_filename,
                    path=os.path.basename(jobs[0].output_path)))
            else:
                notify("File Converter",
                       _("{done}/{total} completed").format(done=done, total=done))
    except Exception:
        pass


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

    # --self-check (diagnostic: verify bundled presets load)
    if args.self_check:
        _self_check()
        return

    # --install
    if args.install:
        from fileconverter.integration import run_install
        run_install()
        return

    # --uninstall
    if args.uninstall:
        from fileconverter.integration import run_uninstall
        run_uninstall()
        return

    # --settings
    if args.settings:
        from fileconverter.ui import UINotAvailable, run_settings_auto
        try:
            run_settings_auto()
        except UINotAvailable:
            print(_("A GUI toolkit (GTK 4 or tkinter) is required for the settings window."),
                  file=sys.stderr)
            sys.exit(1)
        return

    # --pick (the frozen binary has no separate fileconverter-pick executable,
    # so the picker has to be reachable through this flag — it is what the
    # Thunar/PCManFM custom actions call)
    if args.pick:
        files = _collect_files(args)
        if not files:
            print(_("Error: no input files specified."), file=sys.stderr)
            sys.exit(1)
        from fileconverter.ui.picker import main as pick_main
        sys.argv = [sys.argv[0]] + files
        pick_main()
        return

    # No arguments at all → first-run check, then show help or run install
    if not args.preset_name and not args.files:
        from fileconverter.integration import is_installed
        if not is_installed():
            print(_("File Converter is not set up yet. Running setup..."))
            print()
            from fileconverter.integration import run_install
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

    from fileconverter.ui import UINotAvailable, run_with_progress_auto
    try:
        run_with_progress_auto(jobs, settings)
    except UINotAvailable:
        if args.verbose:
            print(_("No GUI toolkit available, running headless."), file=sys.stderr)
        _run_headless(jobs, settings.max_simultaneous_conversions)   # exits 1 on failure
        return

    # The window reports failures visually, but a terminal or a script that
    # called us gets nothing back — so mirror the headless behaviour: print
    # what failed and exit non-zero.
    failed = [j for j in jobs if j.state == ConversionState.FAILED]
    if failed:
        for j in failed:
            print(_("FAILED: {name} — {error}").format(
                name=j.input_filename, error=j.error_message), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

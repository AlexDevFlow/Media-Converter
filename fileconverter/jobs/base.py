"""Base ConversionJob — ported from ConversionJob.cs."""

from __future__ import annotations
import os
import shutil
import threading
import time
from enum import Enum
from pathlib import Path

from fileconverter.i18n import _
from fileconverter.jobs.proc import Cancelled
from fileconverter.path_helpers import generate_output_path, generate_unique_path
from fileconverter.presets import ConversionPreset


class ConversionState(Enum):
    UNKNOWN = "unknown"
    READY = "ready"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    FAILED = "failed"


class ConversionJob:
    def __init__(self, preset: ConversionPreset, input_path: str):
        self.preset = preset
        self.input_path = os.path.abspath(input_path)
        self.output_paths: list[str] = []
        self.current_output_index: int = 0
        self.state = ConversionState.UNKNOWN
        self.progress: float = 0.0
        self.start_time: float = 0.0
        self.error_message: str = ""
        self.user_state: str = _("Preparing...")
        self._cancel_requested = False
        self._cancel_parent: ConversionJob | None = None
        self._lock = threading.Lock()

    @property
    def output_path(self) -> str:
        if not self.output_paths:
            return ""
        idx = max(0, min(self.current_output_index, len(self.output_paths) - 1))
        return self.output_paths[idx]

    @property
    def input_filename(self) -> str:
        return os.path.basename(self.input_path)

    @property
    def cancel_requested(self) -> bool:
        if self._cancel_requested:
            return True
        # Sub-jobs (GIF's two-step pipeline, document → PDF → image) are
        # separate objects; without following the link, cancelling the visible
        # job would leave the inner tool running.
        parent = self._cancel_parent
        return parent.cancel_requested if parent is not None else False

    def request_cancel(self) -> None:
        self._cancel_requested = True

    def link_cancel(self, parent: ConversionJob) -> None:
        """Make this (internal) job cancel together with the user-facing one."""
        self._cancel_parent = parent

    def prepare(self) -> None:
        """Generate output paths and validate.

        For multi-output conversions (e.g. one image per PDF page) the template
        may not differentiate pages — the default ``(p)(f)`` has no page token,
        so every page would resolve to the same path and clobber the previous
        one. When that happens we append a 1-based page number, and we reserve
        each chosen path so no two outputs in the batch ever collide.
        """
        num_outputs = self._get_output_files_count()
        self.output_paths = []

        differentiates = True
        if num_outputs > 1:
            first = generate_output_path(
                self.input_path, self.preset.output_type,
                self.preset.output_template, number_index=0, number_max=num_outputs)
            second = generate_output_path(
                self.input_path, self.preset.output_type,
                self.preset.output_template, number_index=1, number_max=num_outputs)
            differentiates = first != second

        reserved: set[str] = set()
        for i in range(num_outputs):
            path = generate_output_path(
                self.input_path,
                self.preset.output_type,
                self.preset.output_template,
                number_index=i,
                number_max=num_outputs,
            )
            if num_outputs > 1 and not differentiates:
                base, ext = os.path.splitext(path)
                path = f"{base}-{i + 1}{ext}"
            path = generate_unique_path(path, reserved=reserved)
            reserved.add(path)
            out_dir = os.path.dirname(path)
            os.makedirs(out_dir, exist_ok=True)
            self.output_paths.append(path)

        self.state = ConversionState.READY
        self._initialize()

    def run(self) -> None:
        """Execute the conversion. Called from a worker thread."""
        # A cancelled job that is still queued must not start: closing the
        # window on a 50-file batch used to convert every remaining file
        # anyway (and then delete the results).
        if self.cancel_requested:
            self.state = ConversionState.FAILED
            self.error_message = _("Cancelled")
            self.user_state = _("Cancelled")
            self._cleanup_outputs()
            return

        self.state = ConversionState.IN_PROGRESS
        self.start_time = time.time()
        self.user_state = _("Converting...")
        try:
            self._convert()
            if self.cancel_requested:
                self.state = ConversionState.FAILED
                self.error_message = _("Cancelled")
                self._cleanup_outputs()
            else:
                self.progress = 1.0
                self.state = ConversionState.DONE
                self.user_state = _("Done")
                self._post_conversion()
        except Cancelled:
            self.state = ConversionState.FAILED
            self.error_message = _("Cancelled")
            self.user_state = _("Cancelled")
            self._cleanup_outputs()
        except Exception as e:
            self.state = ConversionState.FAILED
            self.error_message = str(e)
            self.user_state = _("Failed")
            self._cleanup_outputs()

    def _get_output_files_count(self) -> int:
        return 1

    def _initialize(self) -> None:
        """Subclass hook for initialization after prepare()."""
        pass

    def _convert(self) -> None:
        """Subclass must implement the actual conversion."""
        raise NotImplementedError

    def _post_conversion(self) -> None:
        """Handle post-conversion actions (archive/delete original)."""
        # Grab timestamps before potentially removing the input file
        try:
            stat = os.stat(self.input_path)
        except OSError:
            stat = None

        action = self.preset.input_post_action
        if action == "delete":
            try:
                os.remove(self.input_path)
            except OSError:
                pass
        elif action == "archive":
            archive_dir = os.path.join(os.path.dirname(self.input_path), "Converted")
            os.makedirs(archive_dir, exist_ok=True)
            dest = os.path.join(archive_dir, os.path.basename(self.input_path))
            dest = generate_unique_path(dest)
            try:
                shutil.move(self.input_path, dest)
            except OSError:
                pass

        # Match output timestamps to input timestamps
        if stat:
            for p in self.output_paths:
                try:
                    if os.path.exists(p):
                        os.utime(p, (stat.st_atime, stat.st_mtime))
                except OSError:
                    pass

    def _cleanup_outputs(self) -> None:
        """Remove incomplete output files on failure."""
        for p in self.output_paths:
            try:
                if os.path.exists(p):
                    os.remove(p)
            except OSError:
                pass

    def _fail(self, message: str) -> None:
        self.state = ConversionState.FAILED
        self.error_message = message
        self.user_state = _("Failed")

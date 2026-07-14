"""tkinter progress window — feature-parity port of progress_window.py (GTK).

Used on macOS (which has no GTK) and as a fallback on Linux systems without
GTK 4 (GH #5). Same model as the GTK window: worker threads mutate the job
objects, the UI polls them every 200 ms from the Tk main loop.
"""

from __future__ import annotations
import os
import sys
import threading
import time
import tkinter as tk
from concurrent.futures import ThreadPoolExecutor
from tkinter import ttk

from fileconverter.config import Settings
from fileconverter.i18n import _
from fileconverter.jobs.base import ConversionJob, ConversionState

_POLL_MS = 200


def _middle_ellipsis(text: str, max_len: int = 48) -> str:
    if len(text) <= max_len:
        return text
    half = (max_len - 1) // 2
    return text[:half] + "…" + text[-half:]


class JobRow(ttk.Frame):
    """A single row showing one conversion job's progress."""

    def __init__(self, parent, job: ConversionJob):
        super().__init__(parent, padding=(12, 6))
        self.job = job
        self.columnconfigure(0, weight=1)

        top = ttk.Frame(self)
        top.grid(row=0, column=0, sticky="ew")
        top.columnconfigure(0, weight=1)

        self.filename_label = ttk.Label(
            top, text=_middle_ellipsis(job.input_filename), anchor="w")
        try:
            import tkinter.font as tkfont
            bold = tkfont.nametofont("TkDefaultFont").copy()
            bold.configure(weight="bold")
            self.filename_label.configure(font=bold)
        except Exception:
            pass
        self.filename_label.grid(row=0, column=0, sticky="ew")

        self.output_label = ttk.Label(
            top, text=f"→ {job.preset.output_type.upper()}", foreground="gray")
        self.output_label.grid(row=0, column=1, padx=8)

        self.cancel_btn = ttk.Button(top, text=_("Cancel"), command=self._on_cancel)
        self.cancel_btn.grid(row=0, column=2)

        bar_row = ttk.Frame(self)
        bar_row.grid(row=1, column=0, sticky="ew", pady=(4, 0))
        bar_row.columnconfigure(0, weight=1)
        self.progress_bar = ttk.Progressbar(bar_row, maximum=1.0, value=0.0)
        self.progress_bar.grid(row=0, column=0, sticky="ew")
        # Aqua progress bars can't draw text on themselves — separate label.
        self.progress_text = ttk.Label(bar_row, text="0%", width=24, anchor="e")
        self.progress_text.grid(row=0, column=1, padx=(8, 0))

        self.status_label = ttk.Label(self, text=_("Waiting..."), foreground="gray")
        self.status_label.grid(row=2, column=0, sticky="w", pady=(2, 0))

        ttk.Separator(self, orient="horizontal").grid(
            row=3, column=0, sticky="ew", pady=(6, 0))

    def _on_cancel(self):
        self.job.request_cancel()
        self.cancel_btn.state(["disabled"])
        self.cancel_btn.configure(text=_("Cancelling..."))

    def update_row(self) -> None:
        state = self.job.state
        progress = self.job.progress
        self.progress_bar.configure(value=min(progress, 1.0))

        if state == ConversionState.IN_PROGRESS:
            elapsed = time.time() - self.job.start_time if self.job.start_time else 0
            if progress > 0.01 and elapsed > 1:
                eta = (elapsed / progress) * (1 - progress)
                if eta < 60:
                    eta_str = _("{seconds}s remaining").format(seconds=int(eta))
                else:
                    eta_str = _("{minutes}m {seconds}s remaining").format(
                        minutes=int(eta // 60), seconds=int(eta % 60))
                self.progress_text.configure(text=f"{progress * 100:.0f}% — {eta_str}")
            else:
                self.progress_text.configure(text=f"{progress * 100:.0f}%")
            self.status_label.configure(text=self.job.user_state)
        elif state == ConversionState.DONE:
            self.progress_bar.configure(value=1.0)
            self.progress_text.configure(text=_("Complete"))
            self.status_label.configure(
                text=f"→ {os.path.basename(self.job.output_path)}")
            self.cancel_btn.grid_remove()
        elif state == ConversionState.FAILED:
            self.progress_text.configure(text=_("Failed"))
            self.status_label.configure(
                text=self.job.error_message or _("Unknown error"), foreground="#c0392b")
            self.cancel_btn.grid_remove()
        elif state == ConversionState.READY:
            self.status_label.configure(text=_("Queued..."))


class ProgressWindow:
    """Main window showing all conversion jobs."""

    def __init__(self, root: tk.Tk, jobs: list, settings: Settings):
        self.root = root
        self.jobs = jobs
        self.settings = settings
        self.job_rows: list[JobRow] = []
        self._auto_close_job = None
        self._auto_close_seconds = settings.exit_delay_seconds
        self._auto_closing = False

        root.title("File Converter")
        root.geometry("560x420")
        root.minsize(480, 260)

        # Scrollable job list
        container = ttk.Frame(root)
        container.pack(fill="both", expand=True)
        self.canvas = tk.Canvas(container, highlightthickness=0)
        scrollbar = ttk.Scrollbar(container, orient="vertical",
                                  command=self.canvas.yview)
        self.list_frame = ttk.Frame(self.canvas)
        self.list_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self._canvas_window = self.canvas.create_window(
            (0, 0), window=self.list_frame, anchor="nw")
        self.canvas.bind(
            "<Configure>",
            lambda e: self.canvas.itemconfigure(self._canvas_window, width=e.width))
        self.canvas.configure(yscrollcommand=scrollbar.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # Bottom bar with auto-close
        ttk.Separator(root, orient="horizontal").pack(fill="x")
        bottom = ttk.Frame(root, padding=(12, 8))
        bottom.pack(fill="x")
        bottom.columnconfigure(0, weight=1)
        self.auto_close_label = ttk.Label(bottom, text="", anchor="w")
        self.auto_close_label.grid(row=0, column=0, sticky="ew")
        self.keep_open_btn = ttk.Button(bottom, text=_("Keep open"),
                                        command=self._cancel_auto_close)
        self.keep_open_btn.grid(row=0, column=1)
        self.keep_open_btn.grid_remove()

        for job in jobs:
            row = JobRow(self.list_frame, job)
            row.pack(fill="x")
            self.job_rows.append(row)

        root.protocol("WM_DELETE_WINDOW", self._on_close_request)
        root.after(_POLL_MS, self._update_ui)

    def start_conversions(self) -> None:
        def _prepare_and_run(job: ConversionJob):
            try:
                job.prepare()
                job.run()
            except Exception as e:
                job.state = ConversionState.FAILED
                job.error_message = str(e)

        def _worker():
            with ThreadPoolExecutor(
                    max_workers=self.settings.max_simultaneous_conversions) as pool:
                pool.map(_prepare_and_run, self.jobs)

        threading.Thread(target=_worker, daemon=True).start()

    # ── UI updates (main thread only) ──

    def _update_ui(self):
        for row in self.job_rows:
            row.update_row()

        all_done = all(j.state in (ConversionState.DONE, ConversionState.FAILED)
                       for j in self.jobs)
        if all_done and self._auto_close_job is None and not self._auto_closing:
            self.auto_close_label.configure(text=self._summary_status())
            if self.settings.exit_when_done:
                self._start_auto_close()

        self.root.after(_POLL_MS, self._update_ui)

    def _summary_status(self) -> str:
        failed = sum(1 for j in self.jobs if j.state == ConversionState.FAILED)
        done = sum(1 for j in self.jobs if j.state == ConversionState.DONE)
        total = len(self.jobs)
        if failed:
            return _("{done}/{total} completed, {failed} failed").format(
                done=done, total=total, failed=failed)
        return _("{done}/{total} completed").format(done=done, total=total)

    def _start_auto_close(self):
        self._auto_closing = True
        self._auto_close_seconds = self.settings.exit_delay_seconds
        self.keep_open_btn.grid()
        self._update_close_label()
        self._auto_close_job = self.root.after(1000, self._auto_close_tick)

    def _auto_close_tick(self):
        self._auto_close_seconds -= 1
        if self._auto_close_seconds <= 0:
            self.root.destroy()
            return
        self._update_close_label()
        self._auto_close_job = self.root.after(1000, self._auto_close_tick)

    def _update_close_label(self):
        self.auto_close_label.configure(text=_("{status} — closing in {seconds}s").format(
            status=self._summary_status(), seconds=self._auto_close_seconds))

    def _cancel_auto_close(self):
        if self._auto_close_job is not None:
            self.root.after_cancel(self._auto_close_job)
            self._auto_close_job = None
        self._auto_closing = False
        self.keep_open_btn.grid_remove()
        self.auto_close_label.configure(text=self._summary_status())

    def _on_close_request(self):
        # Ask running jobs to stop (kills their ffmpeg/magick subprocesses),
        # then close. A short grace period lets the workers see the flag.
        for job in self.jobs:
            if job.state in (ConversionState.READY, ConversionState.IN_PROGRESS,
                             ConversionState.UNKNOWN):
                job.request_cancel()
        self.root.after(250, self.root.destroy)


def run_with_progress(jobs: list, settings: Settings) -> None:
    """Launch the tkinter progress window and run conversions."""
    root = tk.Tk()

    # Finder-launched processes open behind other windows; nudge to front.
    if sys.platform == "darwin":
        try:
            root.lift()
            root.attributes("-topmost", True)
            root.after(700, lambda: root.attributes("-topmost", False))
        except tk.TclError:
            pass

    win = ProgressWindow(root, jobs, settings)
    win.start_conversions()
    root.mainloop()

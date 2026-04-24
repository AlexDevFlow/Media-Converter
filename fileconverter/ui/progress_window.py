"""GTK 4 progress window — ported from MainWindow.xaml / ConversionJobControl.xaml."""

from __future__ import annotations
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, GLib, Adw, Pango

from fileconverter.config import Settings
from fileconverter.i18n import _
from fileconverter.jobs.base import ConversionJob, ConversionState


class JobRow(Gtk.Box):
    """A single row showing one conversion job's progress."""

    def __init__(self, job: ConversionJob):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.job = job
        self.set_margin_start(12)
        self.set_margin_end(12)
        self.set_margin_top(6)
        self.set_margin_bottom(6)

        # Top row: filename and output type
        top = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.filename_label = Gtk.Label(
            label=job.input_filename, xalign=0, hexpand=True,
            ellipsize=Pango.EllipsizeMode.MIDDLE,
        )
        self.filename_label.add_css_class("heading")
        top.append(self.filename_label)

        self.output_label = Gtk.Label(label=f"→ {job.preset.output_type.upper()}")
        self.output_label.add_css_class("dim-label")
        top.append(self.output_label)

        self.cancel_btn = Gtk.Button(label=_("Cancel"))
        self.cancel_btn.add_css_class("destructive-action")
        self.cancel_btn.connect("clicked", self._on_cancel)
        top.append(self.cancel_btn)
        self.append(top)

        # Progress bar
        self.progress_bar = Gtk.ProgressBar(show_text=True)
        self.append(self.progress_bar)

        # Status row
        self.status_label = Gtk.Label(label=_("Waiting..."), xalign=0)
        self.status_label.add_css_class("dim-label")
        self.append(self.status_label)

        # Separator
        self.append(Gtk.Separator())

    def _on_cancel(self, _btn):
        self.job.request_cancel()
        self.cancel_btn.set_sensitive(False)
        self.cancel_btn.set_label(_("Cancelling..."))

    def update(self) -> None:
        """Update UI from job state. Must be called on the GTK main thread."""
        state = self.job.state
        progress = self.job.progress

        self.progress_bar.set_fraction(min(progress, 1.0))

        if state == ConversionState.IN_PROGRESS:
            elapsed = time.time() - self.job.start_time if self.job.start_time else 0
            if progress > 0.01 and elapsed > 1:
                eta = (elapsed / progress) * (1 - progress)
                if eta < 60:
                    eta_str = _("{seconds}s remaining").format(seconds=int(eta))
                else:
                    eta_str = _("{minutes}m {seconds}s remaining").format(
                        minutes=int(eta // 60), seconds=int(eta % 60))
                self.progress_bar.set_text(f"{progress * 100:.0f}% — {eta_str}")
            else:
                self.progress_bar.set_text(f"{progress * 100:.0f}%")
            self.status_label.set_label(self.job.user_state)
        elif state == ConversionState.DONE:
            self.progress_bar.set_fraction(1.0)
            self.progress_bar.set_text(_("Complete"))
            self.status_label.set_label(f"→ {os.path.basename(self.job.output_path)}")
            self.cancel_btn.set_visible(False)
            self.progress_bar.add_css_class("success")
        elif state == ConversionState.FAILED:
            self.progress_bar.set_text(_("Failed"))
            self.status_label.set_label(self.job.error_message or _("Unknown error"))
            self.cancel_btn.set_visible(False)
            self.progress_bar.add_css_class("error")
        elif state == ConversionState.READY:
            self.status_label.set_label(_("Queued..."))


class ProgressWindow(Gtk.ApplicationWindow):
    """Main window showing all conversion jobs."""

    def __init__(self, app: Gtk.Application, jobs: list[ConversionJob], settings: Settings):
        super().__init__(application=app, title="File Converter", default_width=550, default_height=400)
        self.jobs = jobs
        self.settings = settings
        self.job_rows: list[JobRow] = []
        self._auto_close_id = None
        self._auto_close_seconds = settings.exit_delay_seconds
        self._closing = False

        # Header
        header = Gtk.HeaderBar()
        self.set_titlebar(header)

        # Scrolled content
        scroll = Gtk.ScrolledWindow(vexpand=True, hexpand=True)
        self.list_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        scroll.set_child(self.list_box)

        # Bottom bar with auto-close
        self.bottom_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.bottom_bar.set_margin_start(12)
        self.bottom_bar.set_margin_end(12)
        self.bottom_bar.set_margin_bottom(8)
        self.bottom_bar.set_margin_top(8)
        self.auto_close_label = Gtk.Label(label="", xalign=0, hexpand=True)
        self.bottom_bar.append(self.auto_close_label)
        self.cancel_close_btn = Gtk.Button(label=_("Keep open"))
        self.cancel_close_btn.connect("clicked", self._cancel_auto_close)
        self.cancel_close_btn.set_visible(False)
        self.bottom_bar.append(self.cancel_close_btn)

        # Main layout
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        main_box.append(scroll)
        main_box.append(Gtk.Separator())
        main_box.append(self.bottom_bar)
        self.set_child(main_box)

        # Create rows for each job
        for job in jobs:
            row = JobRow(job)
            self.job_rows.append(row)
            self.list_box.append(row)

        # Start periodic UI updates
        GLib.timeout_add(200, self._update_ui)

    def start_conversions(self) -> None:
        """Launch conversion worker threads."""
        def _prepare_and_run(job: ConversionJob):
            try:
                job.prepare()
                job.run()
            except Exception as e:
                job.state = ConversionState.FAILED
                job.error_message = str(e)

        def _worker():
            with ThreadPoolExecutor(max_workers=self.settings.max_simultaneous_conversions) as pool:
                pool.map(_prepare_and_run, self.jobs)

        thread = threading.Thread(target=_worker, daemon=True)
        thread.start()

    def _update_ui(self) -> bool:
        """Called periodically to refresh job rows."""
        if self._closing:
            return False

        for row in self.job_rows:
            row.update()

        # Check if all jobs are done
        all_done = all(j.state in (ConversionState.DONE, ConversionState.FAILED) for j in self.jobs)
        if all_done and self._auto_close_id is None and self.settings.exit_when_done:
            self._start_auto_close()

        return True

    def _start_auto_close(self) -> None:
        self._auto_close_seconds = self.settings.exit_delay_seconds
        self.cancel_close_btn.set_visible(True)
        self._auto_close_id = GLib.timeout_add(1000, self._auto_close_tick)
        self._update_close_label()

    def _auto_close_tick(self) -> bool:
        self._auto_close_seconds -= 1
        if self._auto_close_seconds <= 0:
            self._closing = True
            self.get_application().quit()
            return False
        self._update_close_label()
        return True

    def _summary_status(self) -> str:
        failed = sum(1 for j in self.jobs if j.state == ConversionState.FAILED)
        done = sum(1 for j in self.jobs if j.state == ConversionState.DONE)
        total = len(self.jobs)
        if failed:
            return _("{done}/{total} completed, {failed} failed").format(
                done=done, total=total, failed=failed)
        return _("{done}/{total} completed").format(done=done, total=total)

    def _update_close_label(self) -> None:
        status = self._summary_status()
        self.auto_close_label.set_label(
            _("{status} — closing in {seconds}s").format(
                status=status, seconds=self._auto_close_seconds))

    def _cancel_auto_close(self, _btn=None) -> None:
        if self._auto_close_id is not None:
            GLib.source_remove(self._auto_close_id)
            self._auto_close_id = None
        self.cancel_close_btn.set_visible(False)
        self.auto_close_label.set_label(self._summary_status())


class ConverterApp(Adw.Application):
    def __init__(self, jobs: list[ConversionJob], settings: Settings):
        super().__init__(application_id="org.fileconverter.app")
        self.jobs = jobs
        self.settings = settings
        self.connect("activate", self._on_activate)

    def _on_activate(self, _app):
        win = ProgressWindow(self, self.jobs, self.settings)
        win.present()
        win.start_conversions()


def run_with_progress(jobs: list[ConversionJob], settings: Settings) -> None:
    """Launch the GTK progress window and run conversions."""
    app = ConverterApp(jobs, settings)
    app.run(None)

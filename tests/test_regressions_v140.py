"""Regression tests for the bugs fixed in v1.4.0.

Each test here failed before its fix. They guard behaviour that is easy to
break silently — data loss, cancelled work that keeps running, a context menu
that disappears — so keep them passing.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

import fcutil
from fileconverter import config
from fileconverter.jobs.base import ConversionJob, ConversionState
from fileconverter.jobs.factory import create_job
from fileconverter.jobs.proc import Cancelled, run_cancellable
from fileconverter.presets import ConversionPreset

REPO = Path(__file__).resolve().parent.parent


# --- Data loss: parallel LibreOffice conversions -----------------------------

@pytest.mark.skipif(not fcutil.HAS_LIBREOFFICE, reason="LibreOffice not available")
def test_parallel_document_conversions_all_produce_output(tmp_path):
    """Two soffice processes sharing a user profile do not both convert: the
    second hands its request to the first and exits 0 having written nothing.
    The batch then reported DONE for files that were never produced — half the
    documents silently vanished."""
    inputs = []
    for i in range(4):
        p = tmp_path / f"doc{i}.txt"
        p.write_text(f"document number {i}\n")
        inputs.append(str(p))

    preset = ConversionPreset(name="To Pdf", output_type="pdf",
                              input_types=["txt"], output_template="(p)(f)")
    jobs = [create_job(preset, f) for f in inputs]

    def work(job):
        job.prepare()
        job.run()

    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(work, jobs))

    for job in jobs:
        assert job.state == ConversionState.DONE, f"{job.input_filename}: {job.error_message}"
        assert os.path.exists(job.output_path), (
            f"{job.input_filename} reported DONE but produced no file — "
            "concurrent LibreOffice instances clobbered each other")
        assert os.path.getsize(job.output_path) > 0


@pytest.mark.skipif(not fcutil.HAS_LIBREOFFICE, reason="LibreOffice not available")
def test_document_job_fails_loudly_when_no_output_is_produced(tmp_path, monkeypatch):
    """A conversion that writes nothing must FAIL, never report success."""
    from fileconverter.jobs import libreoffice

    src = tmp_path / "doc.txt"
    src.write_text("hello\n")

    # A "LibreOffice" that exits 0 and produces nothing at all.
    fake = tmp_path / "soffice"
    fake.write_text("#!/bin/sh\nexit 0\n")
    fake.chmod(0o755)
    monkeypatch.setattr(libreoffice.LibreOfficeJob, "_find_libreoffice",
                        staticmethod(lambda: str(fake)))

    preset = ConversionPreset(name="To Pdf", output_type="pdf", input_types=["txt"])
    job = create_job(preset, str(src))
    job.prepare()
    job.run()

    assert job.state == ConversionState.FAILED
    assert not os.path.exists(job.output_path)


# --- Data loss: output-path collisions across concurrent jobs ---------------

def test_two_inputs_never_share_an_output_path(tmp_path):
    """a.jpg and a.gif both map to a.png with the default template. Prepared
    concurrently, each used to find the path free and claim it — one output
    silently overwrote the other, and with delete both inputs were destroyed."""
    from fileconverter.jobs.base import prepare_all
    from fileconverter.path_helpers import _claimed_paths

    (tmp_path / "a.jpg").write_bytes(b"jpg")
    (tmp_path / "a.gif").write_bytes(b"gif")
    preset = ConversionPreset(name="To Png", output_type="png",
                              input_types=["jpg", "gif"], output_template="(p)(f)")
    jobs = [create_job(preset, str(tmp_path / n)) for n in ("a.jpg", "a.gif")]
    try:
        prepare_all(jobs)
        outs = {j.output_paths[0] for j in jobs}
        assert len(outs) == 2, f"two jobs claimed the same output: {outs}"
    finally:
        for j in jobs:
            for p in j.output_paths:
                _claimed_paths.discard(p)


def test_input_is_never_deleted_when_no_output_was_produced(tmp_path, monkeypatch):
    """input_post_action=delete must destroy the original only when the
    conversion actually produced a file."""
    src = tmp_path / "keep.mkv"
    src.write_bytes(b"data")
    preset = ConversionPreset(name="x", output_type="mp4", input_types=["mkv"],
                              input_post_action="delete")
    job = create_job(preset, str(src))
    job.prepare()
    # A conversion that "succeeds" without writing anything.
    job._convert = lambda: None  # type: ignore[assignment]
    job.run()

    assert src.exists(), "the original was deleted despite no output"
    assert job.state == ConversionState.FAILED


def test_failed_job_never_deletes_another_jobs_finished_output(tmp_path):
    """The losing side of a path collision must not remove a file it did not
    create — that used to delete a completed conversion whose input was
    already gone."""
    shared = tmp_path / "out.mp4"
    shared.write_bytes(b"job A's finished output")

    preset = ConversionPreset(name="x", output_type="mp4", input_types=["mkv"])
    job = create_job(preset, str(tmp_path / "b.mkv"))
    job.output_paths = [str(shared)]
    job._preexisting = {str(shared)}   # it was there before this job ran
    job._cleanup_outputs()

    assert shared.exists(), "cleanup deleted another job's pre-existing output"


# --- Data loss: shared temp files across concurrent jobs --------------------

@pytest.mark.skipif(not fcutil.HAS_FFMPEG, reason="ffmpeg not available")
def test_same_named_videos_produce_distinct_gifs(tmp_path):
    """Two files both called x.mp4 in different folders shared a palette temp
    path derived from the basename, so one GIF was encoded with the other's
    colours — and reported DONE."""
    from fileconverter.jobs.base import prepare_all

    d1, d2 = tmp_path / "d1", tmp_path / "d2"
    d1.mkdir(); d2.mkdir()

    def make(color, path):
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                        "-f", "lavfi", "-i", f"color={color}:s=32x32:d=1",
                        "-pix_fmt", "yuv420p", str(path)], check=True)
    make("green", d1 / "x.mp4")
    make("red", d2 / "x.mp4")

    preset = ConversionPreset(name="To Gif", output_type="gif",
                              input_types=["mp4"], output_template="(p)(f)")
    jobs = [create_job(preset, str(d / "x.mp4")) for d in (d1, d2)]
    prepare_all(jobs)

    def run(j):
        j.run()

    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(run, jobs))

    import hashlib
    digests = [hashlib.md5((d / "x.gif").read_bytes()).hexdigest()
               for d in (d1, d2)]
    assert digests[0] != digests[1], "the two GIFs are byte-identical — palette collision"


# --- Numeric / codec edge cases (silent-wrong output) -----------------------

def _probe_dims(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height", "-of", "csv=p=0", path],
        capture_output=True, text=True)
    return out.stdout.strip()


def test_unknown_codec_is_rejected_not_silently_h264():
    """An unknown video_codec used to be silently encoded as H.264 and
    reported as the requested format."""
    preset = ConversionPreset(name="x", output_type="mp4", input_types=["mp4"],
                              settings={"video_codec": "h266"})
    job = create_job(preset, "/tmp/whatever.mp4")
    with pytest.raises(RuntimeError, match="Unknown video codec"):
        job._build_arguments() if hasattr(job, "_build_arguments") else job._initialize()


@pytest.mark.skipif(not fcutil.HAS_FFMPEG, reason="ffmpeg not available")
def test_fractional_scale_is_not_truncated(tmp_path):
    """video_scale 1.25 was formatted with %.2g → "1.2", silently resizing to
    the wrong dimensions."""
    src = tmp_path / "v.mp4"
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                    "-f", "lavfi", "-i", "testsrc=d=1:s=200x100:r=10",
                    "-pix_fmt", "yuv420p", str(src)], check=True)
    preset = ConversionPreset(name="x", output_type="mp4", input_types=["mp4"],
                              settings={"video_scale": 1.25, "video_codec": "h264"})
    job = create_job(preset, str(src))
    job.prepare(); job.run()
    assert job.state == ConversionState.DONE, job.error_message
    assert _probe_dims(job.output_path) == "250,100" or \
        _probe_dims(job.output_path).startswith("250")


@pytest.mark.skipif(not fcutil.HAS_FFMPEG, reason="ffmpeg not available")
def test_arbitrary_and_negative_rotation_is_applied(tmp_path):
    """video_rotation -90 was silently ignored (only 90/180/270 matched)."""
    src = tmp_path / "v.mp4"
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                    "-f", "lavfi", "-i", "testsrc=d=1:s=200x100:r=10",
                    "-pix_fmt", "yuv420p", str(src)], check=True)
    preset = ConversionPreset(name="x", output_type="mp4", input_types=["mp4"],
                              settings={"video_rotation": -90, "video_codec": "h264"})
    job = create_job(preset, str(src))
    job.prepare(); job.run()
    assert job.state == ConversionState.DONE, job.error_message
    assert _probe_dims(job.output_path) == "100,200", "rotation was ignored"


@pytest.mark.skipif(not fcutil.HAS_FFMPEG, reason="ffmpeg not available")
def test_extreme_quality_never_yields_a_garbage_avi(tmp_path):
    """AVI accepted a negative mpeg4 qscale from video_quality=63 and wrote a
    garbage file reported as Done."""
    src = tmp_path / "v.mp4"
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                    "-f", "lavfi", "-i", "testsrc=d=1:s=120x80:r=10",
                    "-pix_fmt", "yuv420p", str(src)], check=True)
    preset = ConversionPreset(name="x", output_type="avi", input_types=["mp4"],
                              settings={"video_quality": 63})
    job = create_job(preset, str(src))
    job.prepare(); job.run()
    assert job.state == ConversionState.DONE, job.error_message
    # The produced AVI must be a valid, probeable file.
    assert subprocess.run(["ffprobe", "-v", "error", job.output_path]).returncode == 0


# --- Claimed-path lifecycle --------------------------------------------------

def test_successful_output_claim_is_released(tmp_path, monkeypatch):
    """The claim must be dropped once the file exists, or re-converting the
    same input after deleting the result yields 'name (2).ext'."""
    from fileconverter.path_helpers import _claimed_paths

    src = tmp_path / "a.txt"
    src.write_text("x")
    preset = ConversionPreset(name="To Pdf", output_type="pdf", input_types=["txt"])
    job = create_job(preset, str(src))
    job.prepare()
    out = job.output_paths[0]
    assert out in _claimed_paths
    # Simulate a successful conversion.
    Path(out).write_text("pdf")
    job.state = ConversionState.IN_PROGRESS
    job._preexisting = set()
    job._convert = lambda: None  # type: ignore[assignment]
    job.run()
    assert job.state == ConversionState.DONE
    assert out not in _claimed_paths, "claim not released after success"


# --- Hostile config ----------------------------------------------------------

@pytest.mark.parametrize("data", [
    "just a string", ["a", "list"], {"presets": None},
    {"max_simultaneous_conversions": 0},
    {"max_simultaneous_conversions": "two"},
    {"max_simultaneous_conversions": 99999},
    {"presets": [{"output_type": "mp4"}]},              # no name
    {"presets": [{"name": "X", "output_type": "mp4", "settings": None}]},
    {"presets": [{"name": "X", "output_type": "mp4", "input_types": None}]},
    {"version": "abc", "exit_delay_seconds": "soon"},
])
def test_hostile_config_never_crashes_and_stays_in_bounds(data):
    """A hand-edited or crash-truncated config must degrade gracefully, never
    raise at startup, and never yield an out-of-range worker count."""
    settings = config.Settings.from_dict(data)
    assert 1 <= settings.max_simultaneous_conversions <= 16
    for p in settings.presets:
        assert isinstance(p.settings, dict)
        assert isinstance(p.input_types, list)


def test_corrupt_config_file_falls_back_to_defaults(tmp_path, monkeypatch):
    """A corrupt settings.yaml is backed up and defaults are used, rather than
    bricking the app with a YAML traceback."""
    cfg_dir = tmp_path / "fileconverter"
    cfg_dir.mkdir()
    (cfg_dir / "settings.yaml").write_text("{ this is: not valid: yaml ]::")
    monkeypatch.setattr(config, "CONFIG_DIR", cfg_dir)
    monkeypatch.setattr(config, "CONFIG_FILE", cfg_dir / "settings.yaml")

    settings = config.load_settings()

    assert len(settings.presets) > 0, "did not fall back to bundled presets"
    assert (cfg_dir / "settings.yaml.bak").exists(), "the bad file was not preserved"


# --- Cancellation ------------------------------------------------------------

def test_cancelled_job_never_starts(tmp_path):
    """Closing the window on a 50-file batch used to convert every queued file
    anyway (and then delete the results)."""
    src = tmp_path / "a.txt"
    src.write_text("x")
    preset = ConversionPreset(name="To Pdf", output_type="pdf", input_types=["txt"])

    job = create_job(preset, str(src))
    job.prepare()
    job.request_cancel()

    started = []
    job._convert = lambda: started.append(True)  # type: ignore[assignment]
    job.run()

    assert not started, "a cancelled job still ran its conversion"
    assert job.state == ConversionState.FAILED
    assert job.error_message == "Cancelled"


def test_run_cancellable_kills_a_running_tool(tmp_path):
    """ImageMagick/LibreOffice used blocking subprocess.run(), so a cancel
    could not stop them — the tool ran to completion with no window."""
    slow = tmp_path / "slow"
    slow.write_text("#!/bin/sh\nsleep 30\n")
    slow.chmod(0o755)

    preset = ConversionPreset(name="x", output_type="pdf", input_types=["txt"])
    job = ConversionJob(preset, str(tmp_path / "in.txt"))

    import threading
    threading.Timer(0.5, job.request_cancel).start()

    t0 = time.monotonic()
    with pytest.raises(Cancelled):
        run_cancellable([str(slow)], job, timeout=30)
    elapsed = time.monotonic() - t0

    assert elapsed < 5, f"the tool was not killed on cancel (took {elapsed:.1f}s)"


def test_cancel_propagates_into_sub_jobs(tmp_path):
    """GIF and document→image conversions build inner jobs; cancelling the
    visible one must stop the inner tool too."""
    preset = ConversionPreset(name="x", output_type="gif", input_types=["png"])
    parent = ConversionJob(preset, str(tmp_path / "in.png"))
    child = ConversionJob(preset, str(tmp_path / "in.png"))
    child.link_cancel(parent)

    assert not child.cancel_requested
    parent.request_cancel()
    assert child.cancel_requested, "cancel did not reach the sub-job"


# --- Preset removal must persist --------------------------------------------

def _isolated_config(tmp_path, monkeypatch):
    cfg_dir = tmp_path / "config" / "fileconverter"
    monkeypatch.setattr(config, "CONFIG_DIR", cfg_dir)
    monkeypatch.setattr(config, "CONFIG_FILE", cfg_dir / "settings.yaml")
    return cfg_dir


def test_removing_a_default_preset_survives_a_reload(tmp_path, monkeypatch):
    """load_settings() re-adds any bundled preset missing from the config, so
    'Remove' in the settings window was undone on the very next load."""
    _isolated_config(tmp_path, monkeypatch)

    settings = config.load_settings()
    victim = settings.presets[0].name
    settings.presets = [p for p in settings.presets if p.name != victim]
    config.save_settings(settings)

    reloaded = config.load_settings()
    names = [p.name for p in reloaded.presets]

    assert victim not in names, f"{victim!r} came back from the dead"
    assert victim in reloaded.removed_presets
    assert len(names) == len(set(names)), "duplicate presets after reload"


def test_upgrading_an_old_config_keeps_custom_presets(tmp_path, monkeypatch):
    """An existing config (no removed_presets key) must upgrade cleanly: custom
    presets kept, new bundled presets added, nothing silently deleted."""
    import yaml

    cfg_dir = _isolated_config(tmp_path, monkeypatch)
    cfg_dir.mkdir(parents=True)
    (cfg_dir / "settings.yaml").write_text(yaml.dump({
        "version": 2,
        "max_simultaneous_conversions": 4,
        "presets": [{
            "name": "My Custom Preset",
            "output_type": "mp4",
            "input_types": ["mkv"],
            "settings": {"video_quality": 42},
        }],
    }))

    settings = config.load_settings()
    names = [p.name for p in settings.presets]

    assert "My Custom Preset" in names, "the user's own preset was dropped"
    assert "To Mp4" in names, "bundled presets were not merged in"
    assert settings.max_simultaneous_conversions == 4
    custom = next(p for p in settings.presets if p.name == "My Custom Preset")
    assert custom.get_setting_int("video_quality") == 42

    # Saving must not now mark every not-yet-merged default as user-removed.
    config.save_settings(settings)
    again = config.load_settings()
    assert len([p.name for p in again.presets]) == len(names)


# --- Selection filtering -----------------------------------------------------

def test_extensionless_file_matches_no_preset():
    """`all([])` is True: a file named README used to be offered every preset."""
    preset = ConversionPreset(name="To Mp4", output_type="mp4", input_types=["mkv"])
    assert not preset.accepts_all_extensions([])
    assert preset.accepts_all_extensions(["mkv"])


# --- Frozen-build environment leak (GH #6) ----------------------------------

def test_notifications_also_get_a_sanitised_env():
    """notify-send is a system binary linked against the very libraries the
    frozen bundle ships — it needs the same treatment as ffmpeg (GH #6)."""
    import inspect
    from fileconverter import ui

    src = inspect.getsource(ui.notify)
    spawns = src.count("subprocess.run(")
    assert src.count("env=system_env()") >= spawns


# --- Context menu integrity --------------------------------------------------

def test_finder_extension_reads_the_real_home_not_its_container():
    """App extensions run sandboxed, where homeDirectoryForCurrentUser returns
    the container — menu.json was never found and the submenu never appeared."""
    src = (REPO / "fileconverter/ui/native/FinderSyncExt.swift").read_text()
    code = "\n".join(line for line in src.splitlines()
                     if not line.strip().startswith("//"))
    assert "getpwuid" in code, "the sandboxed extension must resolve the real home"
    assert "homeDirectoryForCurrentUser" not in code


def test_quick_actions_are_written_when_the_host_app_is_missing(monkeypatch, tmp_path):
    """pluginkit's registration outlives a deleted app bundle. Trusting it
    alone left the user with neither a submenu nor Quick Actions."""
    if sys.platform != "darwin":
        pytest.skip("macOS-only integration")
    from fileconverter.integration import macos

    monkeypatch.setattr(macos, "SERVICES_DIR", tmp_path / "Services")
    monkeypatch.setattr(macos, "HOST_APP", tmp_path / "Gone.app")   # not on disk
    monkeypatch.setattr(macos, "_extension_enabled", lambda: True)  # but registered
    monkeypatch.setattr(macos, "_pbs_flush", lambda: None)

    count = macos.refresh_services(quiet=True)

    assert count > 1, "no per-preset Quick Actions were written as a fallback"


def test_dolphin_writes_to_a_single_service_dir(tmp_path, monkeypatch):
    """Modern KIO scans both service-menu dirs; writing to both would list
    every conversion twice."""
    from fileconverter.integration import install

    monkeypatch.setattr(install.Path, "home", staticmethod(lambda: tmp_path))
    settings = config.Settings(presets=[
        ConversionPreset(name="To Mp4", output_type="mp4", input_types=["mkv"]),
    ])
    monkeypatch.setattr(config, "load_settings", lambda: settings)

    install._install_dolphin_service_menu()

    written = [d for d in install._dolphin_service_dirs()
               if d.exists() and any(d.glob("fileconverter*.desktop"))]
    assert len(written) == 1, f"service menus written to {len(written)} dirs — duplicates"


# --- prepare() is atomic in its path claims ---------------------------------

def test_failed_prepare_releases_its_path_claims(tmp_path):
    """If prepare() raises after claiming an output path (an unknown codec
    raising in _initialize), the claim must be released, or a same-name job
    later in the batch is needlessly bumped to (2)."""
    from fileconverter.path_helpers import _claimed_paths

    src = tmp_path / "v.mp4"
    src.write_bytes(b"x")
    preset = ConversionPreset(name="x", output_type="mp4", input_types=["mp4"],
                              settings={"video_codec": "nope"})
    job = create_job(preset, str(src))
    before = set(_claimed_paths)
    with pytest.raises(Exception):
        job.prepare()
    assert set(_claimed_paths) == before, "prepare() leaked a path claim on failure"


# --- tkinter Keep-open must actually keep the window open --------------------

def test_tk_keep_open_is_sticky():
    """Clicking Keep open must not let the next poll restart the countdown."""
    import types

    # tkinter is an optional dependency (absent on the macOS CI runner, and on
    # any Python built without it) — the tk UI is only ever a fallback.
    pytest.importorskip("tkinter", reason="tkinter not available")
    from fileconverter.ui import progress_window_tk as m

    # A stand-in window with just the auto-close state and methods.
    w = types.SimpleNamespace(
        _auto_close_job="job", _auto_closing=True, _kept_open=False,
        keep_open_btn=types.SimpleNamespace(grid_remove=lambda: None),
        auto_close_label=types.SimpleNamespace(configure=lambda **k: None),
        _summary_status=lambda: "done",
        root=types.SimpleNamespace(after_cancel=lambda j: None),
    )
    m.ProgressWindow._cancel_auto_close(w)
    assert w._kept_open is True and w._auto_close_job is None

    # The guard the poll uses must now block a restart.
    all_done = True
    should_restart = (all_done and w._auto_close_job is None
                      and not w._auto_closing and not w._kept_open)
    assert not should_restart, "Keep open did not stick — countdown would restart"


def test_tk_add_preset_dedups_names():
    """Adding presets without renaming must not create unreachable duplicates."""
    import types

    pytest.importorskip("tkinter", reason="tkinter not available")
    from fileconverter.ui import settings_window_tk as m

    presets = [ConversionPreset(name="To Mp4", output_type="mp4", input_types=["mkv"])]
    w = types.SimpleNamespace(
        settings=types.SimpleNamespace(presets=presets),
        _refresh_preset_list=lambda: None,
        preset_list=types.SimpleNamespace(
            selection_clear=lambda *a: None, selection_set=lambda *a: None,
            see=lambda *a: None),
        _on_preset_selected=lambda: None,
        _mark_modified=lambda: None,
    )
    m.SettingsWindow._on_add_preset(w)
    m.SettingsWindow._on_add_preset(w)
    m.SettingsWindow._on_add_preset(w)

    names = [p.name for p in presets]
    assert len(names) == len(set(names)), f"duplicate preset names: {names}"


# --- Routing: ICO/JP2 handle non-ffmpeg-decodable inputs --------------------

@pytest.mark.skipif(not fcutil.HAS_IMAGEMAGICK, reason="ImageMagick not available")
def test_ico_from_svg_via_imagemagick(tmp_path):
    """To Ico used to route every input to ffmpeg, which cannot decode SVG/raw/
    PDF; those files always failed while every other image preset handled
    them."""
    svg = tmp_path / "logo.svg"
    svg.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="300" '
                   'height="200"><rect width="300" height="200" fill="green"/></svg>')
    preset = ConversionPreset(name="To Ico", output_type="ico",
                              input_types=["svg", "png"])
    job = create_job(preset, str(svg))
    job.prepare(); job.run()
    assert job.state == ConversionState.DONE, job.error_message
    assert os.path.getsize(job.output_path) > 0


@pytest.mark.skipif(not fcutil.HAS_IMAGEMAGICK, reason="ImageMagick not available")
def test_jp2_from_svg_when_delegate_missing(tmp_path):
    """JP2 without the OpenJPEG delegate (Homebrew) must still handle inputs
    ffmpeg can't decode, by rasterising through ImageMagick first."""
    svg = tmp_path / "logo.svg"
    svg.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="200" '
                   'height="200"><rect width="200" height="200" fill="blue"/></svg>')
    preset = ConversionPreset(name="To Jp2", output_type="jp2",
                              input_types=["svg", "png"])
    job = create_job(preset, str(svg))
    job.prepare(); job.run()
    assert job.state == ConversionState.DONE, job.error_message
    assert os.path.getsize(job.output_path) > 0


# --- Output templates --------------------------------------------------------

def test_template_without_path_token_anchors_to_input_dir(tmp_path):
    """A template like "(f)" yields a bare filename; it must resolve next to
    the input, not in the process CWD (and never crash os.makedirs(''))."""
    from fileconverter.path_helpers import generate_output_path

    src = tmp_path / "clip.mkv"
    out = generate_output_path(str(src), "mp4", "(f)")
    assert os.path.dirname(out) == str(tmp_path)

    out2 = generate_output_path(str(src), "mp4", "converted_(f)")
    assert os.path.dirname(out2) == str(tmp_path)
    assert os.path.basename(out2) == "converted_clip.mp4"


# --- Deterministic language detection ---------------------------------------

@pytest.mark.parametrize("lang,expected", [
    ("zh", "zh_CN"), ("pt", "pt_BR"), ("sr", "sr_Cyrl"),
    ("sr@latin", "sr_Latn"), ("it_IT", "it_IT"), ("de", "de_DE"),
])
def test_language_detection_is_deterministic(lang, expected, monkeypatch):
    """A bare prefix must resolve to the same shipped variant every launch
    (the old set iteration flipped zh Simplified/Traditional per run)."""
    from fileconverter import i18n

    for var in ("LANGUAGE", "LC_ALL", "LC_MESSAGES", "LANG"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("LANG", lang)
    assert i18n.detect_system_language() == expected


# --- Silent input to an audio format ----------------------------------------

@pytest.mark.skipif(not fcutil.HAS_FFMPEG, reason="ffmpeg not available")
@pytest.mark.parametrize("out_type", ["mp3", "flac", "wav", "aac", "ogg", "aiff"])
def test_silent_video_to_audio_fails_with_a_readable_message(tmp_path, out_type):
    """Converting a video with no audio track (a screen recording, a clip made
    from a GIF) to an audio format used to fail with whatever ffmpeg said —
    "Error opening output file x.mp3" for MP3, "Error sending frames to
    consumers" for FLAC. Neither mentions the real problem."""
    from fileconverter.jobs.base import prepare_all

    silent = tmp_path / "silent.mkv"
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                    "-f", "lavfi", "-i", "testsrc=d=1:s=64x64:r=10",
                    "-pix_fmt", "yuv420p", str(silent)], check=True)

    preset = ConversionPreset(name=f"To {out_type}", output_type=out_type,
                              input_types=["mkv"])
    job = create_job(preset, str(silent))
    prepare_all([job])
    job.run()

    assert job.state == ConversionState.FAILED
    assert "no audio track" in job.error_message.lower(), job.error_message
    for p in job.output_paths:
        assert not os.path.exists(p), "left a phantom output behind"


@pytest.mark.skipif(not fcutil.HAS_FFMPEG, reason="ffmpeg not available")
def test_video_with_audio_still_converts(tmp_path):
    """Guard for the fix above: the ordinary case must be untouched."""
    from fileconverter.jobs.base import prepare_all

    src = tmp_path / "clip.mp4"
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                    "-f", "lavfi", "-i", "testsrc=d=1:s=64x64:r=10",
                    "-f", "lavfi", "-i", "sine=d=1",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
                    "-shortest", str(src)], check=True)

    for out_type in ("mp3", "flac"):
        preset = ConversionPreset(name=f"To {out_type}", output_type=out_type,
                                  input_types=["mp4"])
        job = create_job(preset, str(src))
        prepare_all([job])
        job.run()
        assert job.state == ConversionState.DONE, job.error_message
        assert os.path.getsize(job.output_path) > 0


def test_run_refuses_a_job_whose_prepare_failed(tmp_path):
    """run() on a job that failed to prepare must do nothing, not execute an
    empty pass list and report DONE for a conversion that never ran."""
    src = tmp_path / "v.mp4"
    src.write_bytes(b"x")
    preset = ConversionPreset(name="x", output_type="mp4", input_types=["mp4"],
                              settings={"video_codec": "nope"})
    job = create_job(preset, str(src))
    try:
        job.prepare()
    except Exception as e:                      # unknown codec
        job.state = ConversionState.FAILED
        job.error_message = str(e)

    job.run()
    assert job.state == ConversionState.FAILED, "an unprepared job reported success"


# --- Headless Linux: GTK must not silently swallow the batch ----------------

def test_gtk_is_skipped_when_it_cannot_open_a_display(monkeypatch):
    """On a headless box GTK imports fine but can't open a display, and the
    failure happens inside the "activate" handler where GObject prints it and
    carries on — so app.run() returned normally and the batch was reported
    finished having converted nothing. Ask GTK up front instead."""
    from fileconverter import ui

    monkeypatch.setattr(ui, "_gtk_can_open_a_display", lambda: False)
    called = []
    monkeypatch.setattr(ui, "_try_tk",
                        lambda fn, *a: called.append(("tk", fn)))

    with pytest.raises(ui.UINotAvailable):
        ui._try_gtk("progress", [], None)

    # ... and the chain moves on to tkinter rather than dying.
    monkeypatch.setattr(sys, "platform", "linux")
    ui.run_with_progress_auto([], None)
    assert called == [("tk", "progress")]


def test_gtk_runtime_error_falls_back(monkeypatch):
    """Belt and braces: if the display vanishes between the check and the
    window, the RuntimeError must become UINotAvailable, not a traceback."""
    from fileconverter import ui

    monkeypatch.setattr(ui, "_gtk_can_open_a_display", lambda: True)

    def boom(*a, **k):
        raise RuntimeError("Gtk couldn't be initialized")

    import fileconverter.ui as ui_mod
    monkeypatch.setitem(sys.modules, "fileconverter.ui.progress_window",
                        types_module_with(run_with_progress=boom))
    with pytest.raises(ui.UINotAvailable):
        ui._try_gtk("progress", [], None)


def types_module_with(**attrs):
    import types as _t
    m = _t.ModuleType("stub")
    for k, v in attrs.items():
        setattr(m, k, v)
    return m


def test_cli_converts_anyway_if_the_window_ran_nothing(tmp_path, monkeypatch):
    """If the GUI returns having started no job and nothing was cancelled, the
    CLI must do the work headless instead of exiting silently."""
    from fileconverter import cli

    src = tmp_path / "a.wav"
    src.write_bytes(b"x")

    ran = []
    monkeypatch.setattr(cli, "_run_headless", lambda jobs, workers: ran.append(jobs))
    monkeypatch.setattr("fileconverter.ui.run_with_progress_auto",
                        lambda jobs, settings: None)   # window that did nothing

    monkeypatch.setattr(sys, "argv",
                        ["fileconverter", "--conversion-preset", "To Mp3", str(src)])
    cli.main()

    assert ran, "the CLI exited without converting and without saying anything"


# --- CLI entry points --------------------------------------------------------

def test_menu_entries_use_an_absolute_quoted_command(tmp_path, monkeypatch):
    """File managers launch menu entries with the login PATH, which usually
    does NOT contain ~/.local/bin — so a bare `Exec=fileconverter` silently
    did nothing. The path must also be quoted: a HOME with a space in it would
    otherwise split into two shell words."""
    from fileconverter.integration import install

    home = tmp_path / "user name"          # a space, on purpose
    (home / ".local" / "bin").mkdir(parents=True)
    (home / ".local" / "bin" / "fileconverter").write_text("#!/bin/sh\n")
    monkeypatch.setattr(install.Path, "home", staticmethod(lambda: home))
    monkeypatch.setattr(install, "LOCAL_BIN", home / ".local" / "bin")
    monkeypatch.setenv("PATH", "/usr/bin:/bin")   # ~/.local/bin NOT on PATH

    settings = config.Settings(presets=[
        ConversionPreset(name="To Mp4", output_type="mp4", input_types=["mkv"]),
    ])
    monkeypatch.setattr(config, "load_settings", lambda: settings)

    install._install_nemo_actions()
    install._install_dolphin_service_menu()
    install._install_desktop_entry()

    written = [
        next((home / ".local/share/nemo/actions").glob("*.nemo_action")),
        next((home / ".local/share/kio/servicemenus").glob("*.desktop")),
        home / ".local/share/applications/fileconverter-settings.desktop",
    ]
    for path in written:
        exec_line = next(l for l in path.read_text().splitlines()
                         if l.startswith("Exec="))
        assert exec_line.startswith('Exec="/'), (
            f"{path.name} does not exec an absolute, quoted path: {exec_line}")


def test_cli_exposes_the_picker():
    """The frozen build is a single binary: without --pick there is no way to
    reach the picker, yet the installer tells Thunar/PCManFM users to call it."""
    out = subprocess.run([sys.executable, "-m", "fileconverter", "--help"],
                         capture_output=True, text=True, cwd=REPO,
                         env={**os.environ, "PYTHONPATH": str(REPO)})
    assert "--pick" in out.stdout


def test_presets_and_translations_ship_inside_the_package():
    """resources/ and locales/ used to live outside the package, so a pip
    install produced a tool with zero presets and no translations."""
    import fileconverter
    from fileconverter.config import DEFAULT_PRESETS_FILE

    package_dir = Path(fileconverter.__file__).parent
    assert (package_dir / "resources" / "default_presets.yaml").exists()
    assert any((package_dir / "locales").glob("*/LC_MESSAGES/fileconverter.mo"))
    assert DEFAULT_PRESETS_FILE.exists()

    pyproject = (REPO / "pyproject.toml").read_text()
    assert "[tool.setuptools.package-data]" in pyproject, (
        "package data is not declared — pip install would not ship the presets")


def test_declared_entry_points_are_importable():
    """A console script pointing at a module that crashes on import (or does
    not exist) is a broken install."""
    import configparser
    import importlib

    text = (REPO / "pyproject.toml").read_text()
    section = text.split("[project.scripts]", 1)[1].split("[", 1)[0]
    targets = [line.split("=", 1)[1].strip().strip('"')
               for line in section.splitlines()
               if "=" in line and not line.strip().startswith("#")]
    assert targets, "no console scripts found"

    for target in targets:
        module_name, func = target.split(":")
        module = importlib.import_module(module_name)
        assert callable(getattr(module, func)), f"{target} is not callable"

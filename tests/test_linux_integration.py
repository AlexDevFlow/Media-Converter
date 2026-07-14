"""Linux integration regressions: subprocess environment (GH #6) and
type-scoped Dolphin service menus (GH #7).

Pure logic — no file manager or frozen binary needed, so these run on any
platform in CI.
"""

from __future__ import annotations

import sys

from fileconverter.helpers import mime_types_for_extensions
from fileconverter.jobs import proc
from fileconverter.presets import ConversionPreset


# --- GH #6: bundled libraries must not leak into system tools ---------------

def test_system_env_is_passthrough_when_not_frozen():
    """From source there is nothing to sanitise — inherit os.environ."""
    assert proc.system_env() is None


def test_system_env_restores_original_ld_library_path(monkeypatch):
    """A frozen build must hand system tools the loader path the user had,
    not the one PyInstaller pointed at the bundle — otherwise /usr/bin/magick
    loads our HarfBuzz and dies with 'undefined symbol' on rolling releases."""
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", "/tmp/_MEI123", raising=False)
    monkeypatch.setenv("LD_LIBRARY_PATH", "/tmp/_MEI123")
    monkeypatch.setenv("LD_LIBRARY_PATH_ORIG", "/opt/user/lib")

    env = proc.system_env()

    assert env["LD_LIBRARY_PATH"] == "/opt/user/lib"
    assert "LD_LIBRARY_PATH_ORIG" not in env


def test_system_env_drops_loader_path_when_user_had_none(monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", "/tmp/_MEI123", raising=False)
    monkeypatch.setenv("LD_LIBRARY_PATH", "/tmp/_MEI123")
    monkeypatch.delenv("LD_LIBRARY_PATH_ORIG", raising=False)

    env = proc.system_env()

    assert "LD_LIBRARY_PATH" not in env


def test_system_env_drops_bundle_paths_but_keeps_user_ones(monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", "/tmp/_MEI123", raising=False)
    monkeypatch.setenv("GI_TYPELIB_PATH", "/tmp/_MEI123/gi_typelibs")
    monkeypatch.setenv("FONTCONFIG_FILE", "/etc/fonts/fonts.conf")  # user's own

    env = proc.system_env()

    assert "GI_TYPELIB_PATH" not in env
    assert env["FONTCONFIG_FILE"] == "/etc/fonts/fonts.conf"


def test_external_tool_calls_pass_a_sanitised_env():
    """Every backend that shells out must route through system_env(); a new
    call site that forgets it would silently reintroduce GH #6."""
    import inspect
    from fileconverter.jobs import ffmpeg, imagemagick, libreoffice

    for module in (ffmpeg, imagemagick, libreoffice):
        src = inspect.getsource(module)
        spawns = src.count("subprocess.run(") + src.count("subprocess.Popen(")
        assert src.count("env=system_env()") >= spawns, (
            f"{module.__name__} spawns {spawns} subprocesses but passes "
            f"system_env() fewer times — a system tool would inherit the "
            f"frozen bundle's loader path (GH #6)."
        )


def test_spawned_tool_really_receives_the_users_loader_path(tmp_path, monkeypatch):
    """End-to-end proof: run a conversion in a simulated frozen build and let
    the tool itself report the environment it was handed. This is the exact
    mechanism behind 'magick: symbol lookup error ... libraqm.so.0' on Arch —
    the child must never see the bundle's library path."""
    import os
    import subprocess

    from fileconverter.jobs.ffmpeg import FFmpegJob

    recorded = tmp_path / "env.txt"
    fake_ffmpeg = tmp_path / "ffmpeg"
    fake_ffmpeg.write_text(
        "#!/bin/sh\n"
        f'printf "%s" "${{LD_LIBRARY_PATH-<unset>}}" > "{recorded}"\n'
        "exit 0\n"
    )
    fake_ffmpeg.chmod(0o755)

    monkeypatch.setenv("PATH", str(tmp_path), prepend=os.pathsep)
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", "/tmp/_MEI_bundle", raising=False)
    monkeypatch.setenv("LD_LIBRARY_PATH", "/tmp/_MEI_bundle")     # PyInstaller's
    monkeypatch.setenv("LD_LIBRARY_PATH_ORIG", "/usr/lib/mine")   # the user's

    src = tmp_path / "clip.mkv"
    src.write_bytes(b"not really a video")
    preset = ConversionPreset(name="To Mp4", output_type="mp4",
                              input_types=["mkv"], settings={"video_quality": 30})

    job = FFmpegJob(preset, str(src))
    job.prepare()
    job.run()

    assert recorded.exists(), "the tool was never spawned"
    assert recorded.read_text() == "/usr/lib/mine", (
        "the spawned tool inherited the frozen bundle's LD_LIBRARY_PATH — "
        "system libraries would load against our bundled ones (GH #6)"
    )


# --- GH #7: context menus must be scoped to the file types they accept ------

def test_mime_types_use_category_globs_for_media():
    assert mime_types_for_extensions(["mp4", "mkv"]) == ["video/*"]
    assert mime_types_for_extensions(["mp3", "flac"]) == ["audio/*"]
    assert mime_types_for_extensions(["png", "jpg"]) == ["image/*"]


def test_mime_types_name_documents_explicitly():
    mimes = mime_types_for_extensions(["pdf", "docx"])
    assert "application/pdf" in mimes
    assert "application/vnd.openxmlformats-officedocument.wordprocessingml.document" in mimes
    # No umbrella glob would wrongly pull in every text file.
    assert not any(m.endswith("/*") for m in mimes)


def test_image_preset_never_matches_video_files():
    """The reported symptom: mkv offered a 'To Jpg' conversion."""
    image_inputs = ["png", "jpg", "webp", "gif"]
    mimes = mime_types_for_extensions(image_inputs)
    assert "video/*" not in mimes
    assert "audio/*" not in mimes


def test_dolphin_service_menus_are_grouped_by_input_type(tmp_path, monkeypatch):
    """One .desktop per input-type group, each with its own MimeType, all
    sharing the submenu name so KIO merges them into one menu."""
    from fileconverter import config
    from fileconverter.integration import install

    monkeypatch.setattr(install.Path, "home", staticmethod(lambda: tmp_path))

    video = ConversionPreset(name="To Mp4", output_type="mp4",
                             input_types=["mkv", "avi", "mp4"])
    image = ConversionPreset(name="To Jpg", output_type="jpg",
                             input_types=["png", "webp"])
    settings = config.Settings(presets=[video, image])
    monkeypatch.setattr(config, "load_settings", lambda: settings)

    assert install._install_dolphin_service_menu()

    menus = sorted((tmp_path / ".local/share/kio/servicemenus").glob("*.desktop"))
    assert len(menus) == 2, "expected one service menu per input-type group"

    by_mime = {}
    for m in menus:
        text = m.read_text()
        mime_line = next(l for l in text.splitlines() if l.startswith("MimeType="))
        by_mime[mime_line] = text
        assert "X-KDE-Submenu=File Converter" in text

    video_menu = next(t for k, t in by_mime.items() if "video/*" in k)
    image_menu = next(t for k, t in by_mime.items() if "image/*" in k)

    # The whole point: the video menu offers no image conversion, and vice versa.
    assert "To Mp4" in video_menu and "To Jpg" not in video_menu
    assert "To Jpg" in image_menu and "To Mp4" not in image_menu


def test_reinstall_removes_stale_service_menus(tmp_path, monkeypatch):
    """Renaming or deleting a preset must not leave a ghost entry behind —
    install, uninstall and is_installed all glob the same pattern."""
    from fileconverter import config
    from fileconverter.integration import install

    monkeypatch.setattr(install.Path, "home", staticmethod(lambda: tmp_path))

    service_dir = tmp_path / ".local/share/kio/servicemenus"
    service_dir.mkdir(parents=True)
    stale = service_dir / "fileconverter.desktop"          # the old monolith
    stale.write_text("[Desktop Entry]\n")
    ghost = service_dir / "fileconverter-group9.desktop"   # a since-removed group
    ghost.write_text("[Desktop Entry]\n")

    settings = config.Settings(presets=[
        ConversionPreset(name="To Mp4", output_type="mp4", input_types=["mkv"]),
    ])
    monkeypatch.setattr(config, "load_settings", lambda: settings)

    install._install_dolphin_service_menu()

    assert not stale.exists()
    assert not ghost.exists()
    assert len(list(service_dir.glob("fileconverter*.desktop"))) == 1

# v1.4.0 — macOS support (and a bunch of fixes)

File Converter runs on macOS now. It's the same tool as on Linux: same engine, the same 46 presets, same CLI, same config format, same 29 languages.

Linux users get something out of this release too. The three open bug reports (#5, #6, #7) are fixed, and while porting to macOS I found and fixed a handful of older bugs that affected Linux as well, including a few that could lose files. If you're on Linux, it's worth updating.

## The Finder menu

`File Converter.app` installs a Finder Sync extension that gives you a proper right-click submenu, the same way the Dolphin/Nemo menus work on Linux:

```
Right-click video.mkv >
  File Converter
  ├── To Mp4
  ├── To Gif
  ├── To Mp3
  ├── ...
  └── Configure presets...
```

It only shows presets that make sense for what you selected (an mkv won't be offered "To Jpg"), and it re-reads your presets on every click, so edits in the settings show up immediately. If you don't have the Xcode command line tools, it falls back to one Quick Action per preset instead.

Conversions run under `File Converter.app`, which matters for one annoying reason: the first time you convert something in Downloads or Desktop, macOS asks for folder permission in the name of "File Converter" rather than "python3.x".

## The windows

The progress window, the picker, and the settings editor are native (SwiftUI), compiled during install. All the actual work stays in Python, the Swift side just draws. If the toolchain isn't there it falls back to tkinter, which also became the fallback on Linux when GTK is missing (see #5).

Video encoding can use VideoToolbox on Apple Silicon if you switch GPU accel to "Auto-detect".

## The Linux bug reports

**#6 — the prebuilt binary broke ImageMagick on Arch.** The PyInstaller bundle ships its own copies of HarfBuzz, Fontconfig and FreeType, and it sets `LD_LIBRARY_PATH` to point at them. Every process it launched inherited that, so the system `magick` loaded *our* HarfBuzz and crashed against Arch's newer `libraqm` (`undefined symbol: hb_ft_font_get_ft_face`). That's also where the wall of Fontconfig warnings came from. ffmpeg, ImageMagick, Ghostscript and LibreOffice now run with the environment your shell would have given them, so they load system libraries again. This is also why building from source always worked. Thanks to @cypress-exe for the report and the diagnosis, which pointed right at it.

**#7 — Dolphin showed every preset on every file.** There was a single service-menu file with `MimeType=application/octet-stream`, so an mkv got offered "To Jpg". Now presets are grouped by the file types they accept, one `.desktop` per group, each with its own `MimeType`. They share the same submenu name so KDE still merges them into one "File Converter" menu — the approach @cypress-exe suggested in the issue. Install/uninstall clean up by glob now, so renaming a preset doesn't leave a dead entry behind.

**#5 — no GTK meant no window.** The UI now tries GTK, then tkinter, then runs headless, so a machine without GTK gets a working progress window instead of a traceback. Thanks @bedokaram187.

## Engine changes

- VideoToolbox joins NVENC/VAAPI for hardware encoding, with the same probe-and-fall-back-to-software logic. HEVC still gets the `hvc1` tag for QuickTime.
- Homebrew's ffmpeg 8 dropped libvorbis and libtheora. WebM audio now uses Opus, Ogg uses the built-in encoder, and OGV gives you a clear "not available on this build" message instead of a cryptic encoder error.
- Some ImageMagick builds (Homebrew's) can't write JP2 and quietly write the input format instead while still exiting 0. Outputs are checked now, and JP2 goes through ffmpeg's encoder when the delegate is missing. ICO gets capped at 256px, and animated GIF to a still image takes the first frame instead of exploding into numbered files.

## Data-safety and reliability pass

I did several audit passes over the engine, installers and UI. A lot of what turned up was old and affected Linux too. The ones that could lose data:

- Two files that mapped to the same output name (`a.jpg` and `a.gif` both becoming `a.png`) would overwrite each other, and with "delete original after conversion" turned on, you'd lose *both* originals while the app said it was done. Output names are reserved before anything runs now, so the second one becomes `a (2).png`.
- The original was deleted or archived without checking the output actually got written. A conversion that finished with no file would take the input down with it. Now the original stays put unless every output exists and isn't empty.
- Running several LibreOffice conversions at once, they'd share one profile and half of them would silently produce nothing while reporting success. Each one gets its own profile now.
- Two videos with the same filename in different folders shared a temporary GIF palette, so one GIF came out with the other's colors. Temp files are per-job now.

Wrong output that looked like success:

- An unknown video codec was quietly encoded as H.264. A rotation like `-90` or `45` was ignored for video (but not for images). A scale of `1.25` got rounded down to `1.2`. These either work correctly now or fail with a message.
- `To Ico` and `To Jp2` failed on SVG, camera raw, PSD and PDF because they were handed to ffmpeg, which can't read those. They go through ImageMagick now.

And some robustness:

- A broken `settings.yaml` (bad YAML, wrong types, `max_workers: 0`) used to crash the app on launch. Now it gets backed up, the defaults load, and every field is range-checked.
- Cancel actually stops ImageMagick and LibreOffice now, not just ffmpeg, and closing the window mid-batch doesn't leave conversions running in the background.
- Smaller stuff: the Linux binary no longer breaks if you delete the folder you unpacked it in, `pip install` actually ships the presets and translations, menu entries use full quoted paths so they work before `~/.local/bin` is on your PATH, and language detection is deterministic.

There's a regression test for each of these. The suite is up to 220 tests from 161.

## Installing

**macOS:** `git clone` then `./install.sh`, or grab `fileconverter-vX.Y.Z-macos.tar.gz` from the release. It installs into a venv under `~/.local/share/fileconverter` — no bundled binary on purpose, since that's what broke on Arch (#6) and tripped Gatekeeper (#5). Needs macOS 13+, the Xcode command line tools, and Homebrew. `fileconverter --uninstall` when you're done.

**Arch:** `yay -S fileconverter`, or `fileconverter-git` to track `main`.

CI builds and tests both platforms now — the Linux binary as before, plus a macOS run with the full 220-test suite and a Swift compile check.

## Thanks

To the people who reported real problems and helped track them down:

- **@cypress-exe** for #6 and #7. The Dolphin fix is the design from the issue, and the #6 diagnosis (bundled libraries vs. Arch's newer ones) was basically the fix.
- **@bedokaram187** for #5, the GTK crash reports that led to the fallback chain.
- **@goofie45** for #3 and the Nemo/Debian testing that got the LibreOffice backend off unoconv in the first place.

🍻

# v1.4.0 — macOS support + reliability hardening

File Converter now runs on macOS, kept 1:1 with the Linux version: same conversion engine, same 46 presets, same CLI, same YAML config and 29-language i18n. **Linux gets fixes too** — the three open bug reports (#5, #6, #7) are addressed (see *Linux fixes*), plus a large **data-safety and reliability pass** that fixed several pre-existing bugs affecting both platforms (see *Reliability & data-safety hardening*).

> Heads-up for existing Linux users: this release fixes real **data-loss** bugs in the conversion engine (details below). Upgrading is recommended.

## Finder integration

- A **Finder Sync extension** (`File Converter.app`, built by the installer) adds a real right-click submenu — `File Converter → To Mp4 / To Gif / …` — matching the Nemo/Dolphin submenu UX. Filtering is per-extension and only shows presets compatible with *every* selected file, so the "every preset on every file type" class of bug (#7) can't happen here by construction. The menu re-reads the preset list on every click, so settings changes apply instantly.
- Without the Xcode Command Line Tools, the installer falls back to one **UTI-scoped Quick Action per preset**, including LaunchServices-resolved dynamic UTIs so formats macOS doesn't claim natively (`.mkv`!) still show the right entries.
- Conversions started from the menu run under `File Converter.app`, so macOS folder-permission prompts (Downloads, Desktop, …) are asked — and stored — under "File Converter", not `python3.x`.

## Native UI

- Progress window, preset picker and the full settings editor are **native SwiftUI**, compiled on the spot by the installer. The Swift binary is a pure renderer: conversions, ETA math, auto-close timing and all translations stay in Python.
- A feature-parity **tkinter** fallback covers systems without the Swift toolchain — and now also serves as the **GTK fallback on Linux**, so a missing GTK never crashes a conversion again (#5).

## Linux fixes

- **Prebuilt binary broke every ImageMagick conversion on Arch** (#6, reported by @cypress-exe). The onefile bundle ships its own HarfBuzz/Fontconfig/FreeType and PyInstaller points `LD_LIBRARY_PATH` at them — and every child process inherited it, so the system's `/usr/bin/magick` loaded *our* HarfBuzz and died with `undefined symbol: hb_ft_font_get_ft_face` against the distro's newer `libraqm`. The same leak produced the Fontconfig warning wall, exactly as the report suspected. External tools (ffmpeg, ImageMagick, Ghostscript, LibreOffice) now run with the loader environment the user's shell would have given them, so they use system libraries again. Running from source was never affected — which is precisely why it worked.
- **Dolphin offered every preset on every file type** (#7, reported by @cypress-exe): a single service-menu file with `MimeType=application/octet-stream` meant an mkv was offered "To Jpg". Presets are now grouped by their input types, one `.desktop` per group with its own `MimeType` (media category globs, explicit MIME types for documents). All groups keep the same `X-KDE-Submenu`, so KIO still merges them into a single "File Converter" menu — the design proposed in the issue. Installs, reinstalls and uninstalls glob `fileconverter*.desktop`, so renamed or deleted presets no longer leave ghost entries.
- **A missing GTK 4 no longer means no UI** (#5, reported by @bedokaram187): the UI chain is now GTK → tkinter → headless, so systems without GTK get a working progress window instead of a traceback.

## Engine

- **VideoToolbox** hardware acceleration (Apple Silicon) joins NVENC/VAAPI, with the same auto-detect probe and software retry; HEVC keeps the `hvc1` tag.
- **Encoder-aware ffmpeg builders**: Homebrew's ffmpeg 8 ships without libvorbis/libtheora — WebM audio now falls back to Opus (spec-valid), Ogg to the built-in encoder, and OGV fails with an actionable message instead of `Error selecting an encoder`.
- **ImageMagick output validation**: builds without a write delegate (e.g. Homebrew lacks OpenJPEG) exit 0 while silently writing the *input* format under the requested extension. Outputs are now format-checked, and JP2 routes through ffmpeg's native JPEG-2000 encoder when needed — PDF pages included. Benefits Linux builds with missing delegates too.
- ICO output is capped at 256×256 (was a hard ffmpeg error on larger images); animated GIF → still-image conversions take the first frame instead of scattering numbered files.

## Reliability & data-safety hardening

This release includes an extensive multi-pass audit of the conversion engine, installers and UI. Several of the bugs found were **pre-existing** and affected the Linux version too. The most important:

**Data loss (both platforms, pre-existing):**
- Two inputs that resolved to the same output name (`a.jpg` + `a.gif` → `a.png` with the default template) silently overwrote each other; with "delete original after conversion" set, **both source files were destroyed** while the UI reported success. Output paths are now claimed process-wide before any conversion starts, so collisions get `name (2).ext`.
- The original file was deleted/archived without verifying the output actually existed — a backend that exited 0 without writing (or a clobbered output) destroyed the input. The original is now kept unless every output is present and non-empty.
- Parallel LibreOffice conversions sharing one profile silently produced nothing for half a batch (each still reported *Done*). Each conversion now gets a private profile.
- Two videos with the same filename in different folders shared a GIF palette temp file, so one GIF came out with the other's colours. Temp files are now per-job.

**Silent-wrong output:**
- An unknown video codec was silently encoded as H.264; a non-orthogonal rotation (`-90`, `45`) was silently ignored for video; a fractional scale like `1.25` was truncated to `1.2`. All now behave correctly or fail with a clear message.
- `To Ico` / `To Jp2` failed on SVG, camera-raw, PSD and PDF inputs (routed to ffmpeg, which can't decode them) — now handled via ImageMagick.

**Robustness:**
- A corrupt or hand-edited `settings.yaml` (bad YAML, wrong types, `max_workers: 0`) no longer crashes the app at startup — it's backed up and defaults are used, and every field is bounds-checked.
- Cancelling a conversion now actually stops ImageMagick and LibreOffice (not just ffmpeg), killing the whole process group; closing the window mid-batch no longer keeps converting invisibly.
- Numerous smaller fixes: the frozen Linux binary no longer breaks when the downloaded folder is deleted; `pip install` now ships the presets and translations; menus use absolute quoted paths so they work before `~/.local/bin` is on `PATH`; system-language detection is deterministic; and more.

Backed by a **220-test** suite (up from 161), including a regression test for every fix above.

## Install

macOS: `git clone` + `./install.sh`, or the new `fileconverter-vX.Y.Z-macos.tar.gz` from the release page. Source install into a private venv under `~/.local/share/fileconverter` — deliberately **no PyInstaller binary**, whose bundled libraries broke against rolling-release systems (#6) and tripped "not authorized to execute" policies (#5). `fileconverter --uninstall` removes everything. Requires macOS 13+, the Xcode Command Line Tools and Homebrew.

CI now builds and tests both platforms: the Linux binary tarball as before, plus the macOS source tarball with the full test suite (220 tests) and Swift compile checks run on a macOS runner.

## Credits

This release owes a lot to the people who took the time to report real-world breakage — their findings drove both the Linux fixes and the design of the macOS port:

- **@cypress-exe** — for #7 and #6. The per-type grouping of KDE service menus is the design proposed in #7, and the diagnosis in #6 (bundled HarfBuzz/Fontconfig vs. rolling-release libraries) pointed straight at the environment leak fixed here.
- **@bedokaram187** — for #5: the GTK crash and execution-policy reports that shaped the toolkit fallback chain.
- **@goofie45** — for #3: Nemo/Debian testing and the unoconv removal that made the LibreOffice backend portable in the first place.

Thank you! 🍻

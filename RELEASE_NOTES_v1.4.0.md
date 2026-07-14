# v1.4.0 — macOS support

File Converter now runs on macOS, kept 1:1 with the Linux version: same conversion engine, same 46 presets, same CLI, same YAML config and 29-language i18n. **No changes for Linux users** — the GTK UI, file-manager integrations and presets are untouched (the engine only *gained* fallbacks, see below).

## Finder integration

- A **Finder Sync extension** (`File Converter.app`, built by the installer) adds a real right-click submenu — `File Converter → To Mp4 / To Gif / …` — matching the Nemo/Dolphin submenu UX. Filtering is per-extension and only shows presets compatible with *every* selected file, so the "every preset on every file type" class of bug (#7) can't happen here by construction. The menu re-reads the preset list on every click, so settings changes apply instantly.
- Without the Xcode Command Line Tools, the installer falls back to one **UTI-scoped Quick Action per preset**, including LaunchServices-resolved dynamic UTIs so formats macOS doesn't claim natively (`.mkv`!) still show the right entries.
- Conversions started from the menu run under `File Converter.app`, so macOS folder-permission prompts (Downloads, Desktop, …) are asked — and stored — under "File Converter", not `python3.x`.

## Native UI

- Progress window, preset picker and the full settings editor are **native SwiftUI**, compiled on the spot by the installer. The Swift binary is a pure renderer: conversions, ETA math, auto-close timing and all translations stay in Python.
- A feature-parity **tkinter** fallback covers systems without the Swift toolchain — and now also serves as the **GTK fallback on Linux**, so a missing GTK never crashes a conversion again (#5).

## Engine

- **VideoToolbox** hardware acceleration (Apple Silicon) joins NVENC/VAAPI, with the same auto-detect probe and software retry; HEVC keeps the `hvc1` tag.
- **Encoder-aware ffmpeg builders**: Homebrew's ffmpeg 8 ships without libvorbis/libtheora — WebM audio now falls back to Opus (spec-valid), Ogg to the built-in encoder, and OGV fails with an actionable message instead of `Error selecting an encoder`.
- **ImageMagick output validation**: builds without a write delegate (e.g. Homebrew lacks OpenJPEG) exit 0 while silently writing the *input* format under the requested extension. Outputs are now format-checked, and JP2 routes through ffmpeg's native JPEG-2000 encoder when needed — PDF pages included. Benefits Linux builds with missing delegates too.
- ICO output is capped at 256×256 (was a hard ffmpeg error on larger images); animated GIF → still-image conversions take the first frame instead of scattering numbered files.

## Install

macOS: `git clone` + `./install.sh`, or the new `fileconverter-vX.Y.Z-macos.tar.gz` from the release page. Source install into a private venv under `~/.local/share/fileconverter` — deliberately **no PyInstaller binary**, whose bundled libraries broke against rolling-release systems (#6) and tripped "not authorized to execute" policies (#5). `fileconverter --uninstall` removes everything. Requires macOS 13+, the Xcode Command Line Tools and Homebrew.

CI now builds and tests both platforms: the Linux binary tarball as before, plus the macOS source tarball with the full test suite (161 tests) and Swift compile checks run on a macOS runner.

## Credits

This release owes a lot to the people who took the time to report real-world breakage on the Linux version — the macOS port was designed around their findings:

- **@cypress-exe** — for #7 (type-aware context menus, including the proposed per-type grouping this port adopts) and #6 (prebuilt-binary library breakage, which motivated the no-binary install design)
- **@bedokaram187** — for #5 (GTK crash and execution-policy reports that shaped the no-GTK, fallback-chain UI)
- **@goofie45** — for #3 (Nemo/Debian testing and the unoconv removal that made the LibreOffice backend portable in the first place)

Thank you! 🍻

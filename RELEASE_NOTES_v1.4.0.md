# v1.4.0 — macOS support + Linux fixes

File Converter now runs on macOS, kept 1:1 with the Linux version: same conversion engine, same 46 presets, same CLI, same YAML config and 29-language i18n. **Linux gets fixes too** — the three open bug reports (#5, #6, #7) are addressed, see *Linux fixes* below.

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

## Install

macOS: `git clone` + `./install.sh`, or the new `fileconverter-vX.Y.Z-macos.tar.gz` from the release page. Source install into a private venv under `~/.local/share/fileconverter` — deliberately **no PyInstaller binary**, whose bundled libraries broke against rolling-release systems (#6) and tripped "not authorized to execute" policies (#5). `fileconverter --uninstall` removes everything. Requires macOS 13+, the Xcode Command Line Tools and Homebrew.

CI now builds and tests both platforms: the Linux binary tarball as before, plus the macOS source tarball with the full test suite (161 tests) and Swift compile checks run on a macOS runner.

## Credits

This release owes a lot to the people who took the time to report real-world breakage — their findings drove both the Linux fixes and the design of the macOS port:

- **@cypress-exe** — for #7 and #6. The per-type grouping of KDE service menus is the design proposed in #7, and the diagnosis in #6 (bundled HarfBuzz/Fontconfig vs. rolling-release libraries) pointed straight at the environment leak fixed here.
- **@bedokaram187** — for #5: the GTK crash and execution-policy reports that shaped the toolkit fallback chain.
- **@goofie45** — for #3: Nemo/Debian testing and the unoconv removal that made the LibreOffice backend portable in the first place.

Thank you! 🍻

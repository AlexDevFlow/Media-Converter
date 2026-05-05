# v1.2.0 — Format coverage expansion

This release closes the gap between what the README promised and what the app actually accepted, and adds the formats users were asking for. **No breaking changes** — your existing presets, custom quality settings, and rotation/scale tweaks are all preserved.

## New output formats (was 17, now 28)

| Category | New |
|---|---|
| **Audio** | M4A, Opus |
| **Video** | MOV |
| **Image** | TIFF, BMP, ICO |
| **Document** | DOCX, ODT, XLSX, ODS, PPTX, ODP — direct office-to-office conversion via LibreOffice (no PDF detour) |

## New input formats (was 62, now 85)

- **Video**: f4v, m2ts, mts, mxf, qt
- **Audio**: aif, dff, dsf, mka, mpc, wv
- **Image**: jp2, pbm, pgm, ppm
- **Document**: csv, epub, html, key, numbers, pages, rtf, txt

## Bug fixes

- **vob** files were listed as supported in the README but rejected by every preset. Now accepted by video/audio/gif presets.
- **To Ico** preset was wired in the codebase but had no entry in the default presets, so the right-click menu never showed it. Now visible.

## Upgrading from v1.1.x

Extract the tarball to a **stable directory** (not `/tmp`, not your Downloads folder — the binary stays where you put it, and the right-click menu will break if you move or delete it later). The recommended layout matches what `--install` already expects:

```bash
# 1. Extract into a versioned directory under ~/.local/share/
mkdir -p ~/.local/share/fileconverter-v1.2.0
tar -xzf fileconverter-v1.2.0-linux-x86_64.tar.gz \
    --strip-components=1 -C ~/.local/share/fileconverter-v1.2.0

# 2. Run the installer (re-points the symlink, regenerates the context menu)
~/.local/share/fileconverter-v1.2.0/install.sh

# 3. Optional — reclaim disk space from the previous release
rm -rf ~/.local/share/fileconverter-v1.1.2/
```

What `install.sh` does on top of an existing v1.1.x install:

- Re-points `~/.local/bin/fileconverter` to the new binary
- Wipes the old Dolphin / Nautilus / Nemo / Thunar / PCManFM context menu entries and rebuilds them for the 31 presets
- Runs a one-shot config migration on `~/.config/fileconverter/settings.yaml`: appends the 12 new preset entries by name and unions input lists for presets that already exist, so newly supported formats become reachable

Your existing customisations (quality, scale, rotation, audio toggles, custom presets you added yourself) are not touched.

> ⚠️ If you had manually unticked an input extension in a preset (e.g. removed `gif` from "To Mp4"), the migration re-adds it once. Untick it again after upgrade if needed.

## Rolling back to v1.1.2

The previous release stays on the [releases page](https://github.com/AlexDevFlow/Media-Converter/releases/tag/v1.1.2). Re-extract that tarball into `~/.local/share/fileconverter-v1.1.2/` and run its `install.sh` — your `settings.yaml` will keep the v1.2.0 entries (harmless on the older binary, which simply ignores presets it doesn't know how to fulfil).

## Notes for power users

- Output coverage is broad but not every input/output combination is meaningful (e.g. `csv → pptx` is rejected at the preset level by design).
- Exotic codec support depends on what your local `ffmpeg`/`imagemagick` was built with — Fedora's `ffmpeg-free` still lacks H.264/H.265 (use RPM Fusion's full ffmpeg).
- The full conversion matrix is **not** exhaustively tested. If a conversion fails, please open an issue with the source file type, target format, and the error message — that's the fastest path to a fix.

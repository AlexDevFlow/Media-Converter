# v1.3.0 — Modern codecs, lossless audio, ebooks & data exports

This release adds 15 new output formats and per-preset video-codec selection, and fixes two latent **data-loss** bugs found while testing the new conversions. **No breaking changes** — your existing presets and custom settings are preserved, and H.264 output is byte-for-byte unchanged.

## New output formats (was 28, now 38)

| Category | New |
|---|---|
| **Video codecs** | H.265/HEVC, AV1, ProRes — selected per preset via `video_codec` on MP4/MKV/MOV (H.264 stays the default) |
| **Audio** | AIFF, WMA, AC3, and ALAC (Apple Lossless, via `audio_codec: alac` on an M4A preset) |
| **Image** | JP2 (JPEG 2000), TGA (Truevision Targa) |
| **Document** | EPUB, RTF, TXT, HTML, CSV (via LibreOffice) |

New default presets: To Mp4 (H.265), To Mkv (H.265), To Mp4 (AV1), To Mov (ProRes), To Aiff, To M4a (Apple Lossless), To Wma, To Ac3, To Jp2, To Tga, To Epub, To Rtf, To Txt, To Html, To Csv. A **Video Codec** dropdown was added to the settings window.

H.265 reuses the existing NVENC/VAAPI hardware-acceleration path and is tagged `hvc1` in MP4/MOV for Apple/QuickTime playback; AV1 (SVT-AV1) and ProRes always encode on the CPU.

## Bug fixes

- **Data loss — multi-page PDF conversions.** Converting a multi-page PDF to an image silently produced only one file: every page resolved to the same output path and overwrote the previous one. Pages are now written to distinct, page-numbered files (`name-1.jp2`, `name-2.jp2`, …). This affected the pre-existing PDF → PNG/JPG/etc. paths too, not just the new image formats.
- **Data loss — same-extension document conversions.** A same-extension conversion (e.g. txt → txt, docx → docx) could move the original input file away, destroying it. Conversions now run through a temporary directory and never touch the input.
- **Hardware acceleration was wrongly disabled on working GPUs.** The NVENC/VAAPI capability probe used a 64×64 test frame that some encoders reject; it now uses a realistic frame size, so "Auto" correctly detects a usable GPU.
- **Invalid codec/container combinations** (e.g. AV1 in MOV, ProRes in MP4) now fail fast with a clear message instead of a cryptic ffmpeg error.
- **EPUB integrity check.** A source that can't become a real EPUB no longer "succeeds" with an empty stub file; it reports a clear error.

## Quality

- Added a 150+-case automated test suite exercising every new format end-to-end against real ffmpeg/LibreOffice/ImageMagick, plus codec/container routing, hardware-accel fallback, unicode/space/shell-metacharacter filenames, output-collision uniqueness, and the data-loss regressions above.
- CI now runs `fileconverter --self-check` after building, verifying the bundled presets actually load in the frozen binary (the old smoke test only ran `--version`).

## Upgrading from v1.2.x

Extract the tarball to a **stable directory** (not `/tmp` or Downloads — the binary stays where you put it and the right-click menu breaks if you move it later):

```bash
mkdir -p ~/.local/share/fileconverter-v1.3.0
tar -xzf fileconverter-v1.3.0-linux-x86_64.tar.gz \
    --strip-components=1 -C ~/.local/share/fileconverter-v1.3.0
~/.local/share/fileconverter-v1.3.0/install.sh
rm -rf ~/.local/share/fileconverter-v1.2.0/   # optional, reclaim space
```

The installer re-points `~/.local/bin/fileconverter`, rebuilds the context-menu entries, and appends the 15 new presets to `~/.config/fileconverter/settings.yaml` by name. Your existing customisations (quality, scale, rotation, custom presets) are not touched.

## Notes for power users

- Codec availability depends on your local `ffmpeg` build (libx265 / libsvtav1 / prores_ks) and `imagemagick` delegates (openjpeg for JP2). Fedora's `ffmpeg-free` lacks H.264/H.265 — use RPM Fusion's full ffmpeg.
- Not every input/output combination is meaningful; the preset layer filters the obvious mismatches. If a conversion fails, please open an issue with the source type, target format, and error message.

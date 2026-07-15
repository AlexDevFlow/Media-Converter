# File Converter for Linux & macOS

Linux and macOS port of [File Converter](https://github.com/Tichau/FileConverter) by Tichau. Right-click files in your file manager, pick a format, convert.

## Support the project :D

If you find this useful, you can [buy me a coffee](https://paypal.me/alextrysh).

## Quick Start

### Linux — download the release tarball

1. Grab `fileconverter-vX.Y.Z-linux-x86_64.tar.gz` from the [Releases page](https://github.com/AlexDevFlow/Media-Converter/releases).
2. Open a terminal in your downloads folder and run:

```bash
tar -xzf fileconverter-v*-linux-x86_64.tar.gz
cd fileconverter-v*
./install.sh
```

The installer detects your file manager and sets up the right-click "File Converter" submenu. The bare `fileconverter` binary is also attached to each release for power users who want to manage placement themselves (`chmod +x fileconverter && ./fileconverter`).

### Linux — run from source

```bash
git clone https://github.com/AlexDevFlow/Media-Converter.git
cd Media-Converter
./install.sh
```

Requires Python 3.9+ and PyYAML (`python3-yaml` on most distros).

### macOS

```bash
git clone https://github.com/AlexDevFlow/Media-Converter.git
cd Media-Converter
./install.sh
```

The installer puts the tool in `~/.local/share/fileconverter` in its own venv
(no PyInstaller binary, so no Gatekeeper headaches), installs the media tools
with [Homebrew](https://brew.sh) if you don't have them, and builds a Finder
Sync extension that adds a real submenu to the right-click menu, just like the
Dolphin/Nemo submenu on Linux:

```
Right-click video.mkv >
  File Converter
  ├── To Mp4
  ├── To Mp4 (low quality)
  ├── To Gif
  ├── To Mp3
  ├── ...
  └── Configure presets...
```

The submenu only shows presets that work for every file you selected. If you
don't have the Swift toolchain, it falls back to one Quick Action per preset
instead (same conversions, just a flatter menu).

Conversions open a native progress window (per-file progress, ETA, cancel),
built by the installer with a tkinter fallback. Settings are native too:
double-click **File Converter.app** in `~/Applications`, or run
`fileconverter --settings`. Video encoding can use Apple's VideoToolbox
hardware acceleration if you turn on "Auto-detect" under GPU accel.

You'll need macOS 13 or newer, the Xcode Command Line Tools
(`xcode-select --install`, which give you Python 3.9+ and the Swift compiler),
and Homebrew for the media tools. If the submenu doesn't show up right away,
restart Finder with `killall Finder`, or check that the extension is enabled in
System Settings → General → Login Items & Extensions. One gotcha with the
tkinter fallback: the Tk that ships with macOS is ancient and draws blank
windows, so `brew install python-tk` if you end up needing it. Uninstall with
`fileconverter --uninstall`.

## How It Works

Right-click files in your file manager. A **File Converter** submenu shows conversion options filtered to the selected file types.

```
Right-click video.mkv >
  File Converter
  ├── To Mp4
  ├── To Mp4 (low quality)
  ├── To Mkv
  ├── To Webm
  ├── To Gif
  ├── To Mp3
  ├── To Ogg
  ├── ...
  └── Configure presets...
```

A progress window shows conversion status with estimated time remaining. Multiple files convert in parallel.

## Supported Formats

### Input (85 formats)

| Category | Formats |
|----------|---------|
| **Video** | 3gp, 3gpp, avi, bik, f4v, flv, m2ts, m4v, mkv, mov, mp4, mts, mxf, mpg, mpeg, ogv, qt, rm, ts, vob, webm, wmv |
| **Audio** | aac, aif, aiff, ape, dff, dsf, flac, m4a, m4b, mka, mp3, mpc, oga, ogg, opus, wav, wma, wv |
| **Image** | arw, avif, bmp, cr2, dds, dng, exr, gif, heic, ico, jfif, jp2, jpg, jpeg, nef, pbm, pgm, png, ppm, psd, raf, svg, tga, tif, tiff, webp, xcf |
| **Document** | csv, doc, docx, epub, html, key, numbers, odp, ods, odt, pages, pdf, ppt, pptx, rtf, txt, xls, xlsx |

### Output (38 formats)

| Category | Formats |
|----------|---------|
| **Video** | MP4, MKV, MOV, WebM, OGV, AVI |
| **Video codecs** | H.264 (default), H.265/HEVC, AV1, ProRes — selectable per preset for MP4/MKV/MOV (see [Video codecs](#video-codecs)) |
| **Audio** | MP3, AAC, M4A (AAC or ALAC), AIFF, OGG, OPUS, FLAC, WAV, WMA, AC3 |
| **Image** | PNG, JPG, WebP, AVIF, JP2, TIFF, BMP, TGA, ICO, GIF |
| **Document** | PDF, DOCX, ODT, RTF, TXT, HTML, EPUB, XLSX, ODS, CSV, PPTX, ODP |

> Note: not every input/output combination is meaningful (e.g. `csv → pptx`),
> and exotic codecs depend on what your local `ffmpeg`/`imagemagick` build
> supports. If a conversion fails, please open an issue with the source file
> type and target format.

## Dependencies

The installer checks for these and tells you what to install.

| Tool | Used for | Required? |
|------|----------|-----------|
| **FFmpeg** | Video and audio conversion | Yes |
| **ImageMagick** | Image conversion, PDF to image | Yes |
| **Ghostscript** | PDF processing | Recommended |
| **LibreOffice** | Office documents (docx, xlsx, pptx) | Optional |

### Install commands by platform

**macOS (Homebrew):**
```bash
brew install ffmpeg imagemagick ghostscript
brew install --cask libreoffice   # optional, for document presets
```

**Ubuntu / Debian:**
```bash
sudo apt install ffmpeg imagemagick ghostscript libreoffice
```

**Fedora:**
```bash
# ffmpeg-free lacks H.264/H.265 encoders. For video presets, install the full
# ffmpeg from RPM Fusion (https://rpmfusion.org/Configuration) instead:
sudo dnf install ffmpeg ImageMagick ghostscript libreoffice-writer libreoffice-calc libreoffice-impress
```

**Arch Linux:**
```bash
sudo pacman -S ffmpeg imagemagick ghostscript libreoffice-still
```

**openSUSE:**
```bash
sudo zypper install ffmpeg ImageMagick ghostscript libreoffice
```

For the Nautilus right-click menu (GNOME/Ubuntu), you also need:

```bash
# Ubuntu/Debian
sudo apt install python3-nautilus

# Fedora
sudo dnf install nautilus-python

# Arch
sudo pacman -S python-nautilus
```

## Usage

### Context menu

Right-click files in your file manager. The submenu only shows presets compatible with the selected files.

Supported file managers:
- **Nautilus** (GNOME/Ubuntu)
- **Nemo** (Cinnamon/Linux Mint)
- **Dolphin** (KDE)
- **Thunar** (XFCE)
- **PCManFM** (LXDE/LXQt)

### Terminal

```bash
# Convert a single file
fileconverter --conversion-preset "To Mp4" video.mkv

# Convert multiple files
fileconverter --conversion-preset "To Mp3" *.wav

# Use a file list
fileconverter --conversion-preset "To Jpg" --input-files list.txt

# Open settings
fileconverter --settings

# Re-run setup
fileconverter --install

# Remove everything
fileconverter --uninstall
```

## Default Presets

| Preset | Output | Notes |
|--------|--------|-------|
| To Mp4 | MP4 | H.264, quality 30, AAC audio |
| To Mp4 (low quality) | MP4 | H.264, quality 20, lower bitrate |
| To Mkv | MKV | H.264, quality 30, AAC audio |
| To Mov | MOV | H.264, quality 30, AAC audio |
| To Webm | WebM | VP9 codec |
| To Ogv | OGV | Theora codec |
| To Avi | AVI | MPEG-4/XviD |
| To Mp4 (H.265) | MP4 | H.265/HEVC, ~half the size of H.264 |
| To Mkv (H.265) | MKV | H.265/HEVC |
| To Mp4 (AV1) | MP4 | AV1 via SVT-AV1, royalty-free |
| To Mov (ProRes) | MOV | ProRes HQ, edit-friendly mezzanine |
| To Gif | GIF | 15fps, palette-optimized |
| To Gif (low quality) | GIF | 10fps, 75% scale |
| To Mp3 | MP3 | VBR ~190kbps |
| To Mp3 (low quality) | MP3 | VBR ~100kbps |
| To Aac | AAC | VBR ~155kbps |
| To M4a | M4A | AAC in MP4 container, ~155kbps |
| To Ogg | OGG | Vorbis ~160kbps |
| To Opus | Opus | ~128kbps |
| To Flac | FLAC | Lossless, max compression |
| To Wav | WAV | 16-bit PCM |
| To Aiff | AIFF | Lossless 16-bit PCM (big-endian) |
| To M4a (Apple Lossless) | M4A | ALAC lossless, Apple ecosystem |
| To Wma | WMA | Windows Media Audio, ~160kbps |
| To Ac3 | AC3 | Dolby Digital, ~192kbps |
| To Png | PNG | Lossless |
| To Jpg | JPG | Quality 85 |
| To Webp | WebP | Quality 85 |
| To Avif | AVIF | Quality 80 |
| To Tiff | TIFF | LZW lossless |
| To Bmp | BMP | Uncompressed |
| To Ico | ICO | Windows icon |
| To Jp2 | JP2 | JPEG 2000, quality 85 |
| To Tga | TGA | Truevision Targa |
| To Pdf | PDF | From images or documents |
| To Docx | DOCX | Word format via LibreOffice |
| To Odt | ODT | OpenDocument Text |
| To Xlsx | XLSX | Excel format via LibreOffice |
| To Ods | ODS | OpenDocument Spreadsheet |
| To Pptx | PPTX | PowerPoint format via LibreOffice |
| To Odp | ODP | OpenDocument Presentation |
| To Epub | EPUB | Ebook (EPUB) via LibreOffice |
| To Rtf | RTF | Rich Text Format via LibreOffice |
| To Txt | TXT | Plain text via LibreOffice |
| To Html | HTML | HTML via LibreOffice |
| To Csv | CSV | From spreadsheets via LibreOffice |

All presets are customizable in the settings window or directly in `~/.config/fileconverter/settings.yaml`. When upgrading from an older version, missing default presets are added automatically on next launch (your customisations are preserved).

## Settings

```bash
fileconverter --settings
```

Or from the context menu: **File Converter > Configure presets...**

### What you can configure

**Global:** max simultaneous conversions, auto-close window, hardware acceleration (Off / Auto / NVENC / VAAPI), UI language.

**Per-preset:** output format, video codec (H.264/H.265/AV1/ProRes), input file types, video quality/encoding speed/scale/rotation, audio bitrate/VBR/CBR/channels, image quality/scale/rotation, output filename template, post-conversion action, custom FFmpeg command override.

### Config file

Settings are stored in YAML at `~/.config/fileconverter/settings.yaml`. Example preset:

```yaml
presets:
  - name: "Video/To Mp4 (720p)"
    output_type: mp4
    input_types: [avi, mkv, mov, mp4, webm, wmv]
    output_template: "(p)(f)"
    input_post_action: none
    settings:
      enable_audio: true
      video_quality: 28
      video_encoding_speed: medium
      video_scale: 0.5
      audio_bitrate: 128
```

### Output filename templates

| Variable | Meaning |
|----------|---------|
| `(p)` or `(path)` | Parent directory of input file |
| `(f)` or `(filename)` | Input filename without extension |
| `(F)` | Input filename uppercase |
| `(o)` or `(outputext)` | Output extension |
| `(i)` or `(inputext)` | Input extension |
| `(p:d)` | ~/Documents/ |
| `(p:m)` | ~/Music/ |
| `(p:v)` | ~/Videos/ |
| `(p:p)` | ~/Pictures/ |
| `(d0)`, `(d1)` | Directory hierarchy levels |
| `(n:i)` | File number in batch |
| `(n:c)` | Total files in batch |
| `(d:FORMAT)` | Current date/time |

Default template is `(p)(f)` (same folder, same name, new extension). If the output file already exists, a number is appended automatically: `file (2).mp4`.

## Languages

The UI is available in 29 languages. On first launch it picks your system language automatically; you can override it from **Settings → Language** (the setting is saved in `~/.config/fileconverter/settings.yaml` and the window rebuilds instantly in the new language).

Shipped locales: Arabic, Chinese (Simplified & Traditional), Czech, Dutch, English, French, German, Greek, Hebrew, Hindi, Hungarian, Indonesian, Italian, Japanese, Korean, Persian, Polish, Portuguese (Brazil & Portugal), Romanian, Russian, Serbian (Cyrillic & Latin), Spanish, Swedish, Thai, Turkish, Ukrainian, Vietnamese.

To add or update a translation, edit [`locales/build.py`](locales/build.py) and run `python3 locales/build.py`. That regenerates each `.po` and compiles `.mo` catalogs into `locales/<lang>/LC_MESSAGES/`.

## Video codecs

MP4, MKV and MOV are containers — the codec inside is chosen per preset via the
`video_codec` setting (or the **Video Codec** dropdown in settings):

| Codec | Setting | Notes |
|-------|---------|-------|
| **H.264** | `h264` (default) | Universal compatibility, hardware-accelerated |
| **H.265 / HEVC** | `hevc` | ~half the size at similar quality; hardware-accelerated; tagged `hvc1` in MP4/MOV for Apple/QuickTime playback |
| **AV1** | `av1` | Royalty-free, smallest files; CPU-only (SVT-AV1) |
| **ProRes** | `prores` | Intra-frame editing mezzanine; keeps 10-bit 4:2:2; CPU-only. `prores_profile` 0–5 (3 = HQ) |

```yaml
presets:
  - name: "To Mp4 (H.265)"
    output_type: mp4
    settings:
      video_codec: hevc
      video_quality: 28
```

H.264 and H.265 use the GPU when hardware acceleration is enabled; AV1 and
ProRes always encode on the CPU.

## Hardware Acceleration

GPU-accelerated video encoding for MP4 and MKV output:

| Mode | GPU | Notes |
|------|-----|-------|
| **Off** | None | Software encoding (default, always works) |
| **Auto** | Auto-detect | Probes your system, picks the best available |
| **NVENC** | NVIDIA | Requires NVIDIA GPU + drivers |
| **VAAPI** | AMD / Intel | Works with Mesa drivers on most Linux systems |

```yaml
hardware_acceleration: auto  # off | auto | nvenc | vaapi
```

If hardware encoding fails, the app falls back to software encoding automatically.

## Building From Source

```bash
git clone https://github.com/AlexDevFlow/Media-Converter.git
cd Media-Converter
./install.sh
```

To build the standalone binary:

```bash
./build.sh
```

Produces `dist/fileconverter`, a standalone executable that bundles Python and all dependencies.

## Uninstalling

```bash
fileconverter --uninstall
```

Removes context menu entries, desktop entry, launcher scripts, and config directory. Does not remove the binary itself.

## Troubleshooting

**The context menu doesn't appear after install.**
Restart your file manager: `nautilus -q` (for GNOME). Then reopen it.

**"No compatible presets" when right-clicking.**
The file extension isn't in any preset's input list. Open settings and add it, or use the terminal.

**Custom FFmpeg commands.**
In a preset's settings, set `enable_ffmpeg_custom_command: true` and `ffmpeg_custom_command: "<your args>"`. The command is inserted between `-i input` and the output path.

**Preset folders in the context menu.**
Use `/` in the preset name. `Video/To Mp4` creates a "Video" submenu containing "To Mp4".

**Wayland support.**
Yes. GTK 4 supports Wayland natively.

## Credits

- Original [File Converter](https://github.com/Tichau/FileConverter) by Adrien Allard (Tichau)
- [FFmpeg](https://ffmpeg.org/), [ImageMagick](https://imagemagick.org/), [Ghostscript](https://ghostscript.com/), [LibreOffice](https://www.libreoffice.org/)

## License

GPLv3. Same as the original File Converter.

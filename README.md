# File Converter for Linux

Linux port of [File Converter](https://github.com/Tichau/FileConverter) by Tichau. Right-click files in your file manager, pick a format, convert.

## Support the project :D

If you find this useful, you can [buy me a coffee](https://paypal.me/alextrysh).

## Quick Start

### Download the binary

1. Download `fileconverter` from the [Releases page](https://github.com/AlexDevFlow/Media-Converter/releases)
2. Open a terminal where you downloaded it:

```bash
chmod +x fileconverter
./fileconverter
```

First run walks you through setup automatically.

### Run from source

```bash
git clone https://github.com/AlexDevFlow/Media-Converter.git
cd Media-Converter
./install.sh
```

Requires Python 3.10+ and PyYAML (`python3-yaml` on most distros).

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

### Input (62 formats)

| Category | Formats |
|----------|---------|
| **Video** | 3gp, 3gpp, avi, bik, flv, m4v, mkv, mov, mp4, mpg, mpeg, ogv, rm, ts, vob, webm, wmv |
| **Audio** | aac, aiff, ape, flac, m4a, m4b, mp3, oga, ogg, opus, wav, wma |
| **Image** | arw, avif, bmp, cr2, dds, dng, exr, gif, heic, ico, jfif, jpg, jpeg, nef, png, psd, raf, svg, tga, tif, tiff, webp, xcf |
| **Document** | doc, docx, odt, pdf, ppt, pptx, odp, ods, xls, xlsx |

### Output (17 formats)

| Category | Formats |
|----------|---------|
| **Video** | MP4, MKV, WebM, OGV, AVI |
| **Audio** | MP3, AAC, OGG, FLAC, WAV |
| **Image** | PNG, JPG, WebP, AVIF, ICO |
| **Document** | PDF, GIF |

## Dependencies

The installer checks for these and tells you what to install.

| Tool | Used for | Required? |
|------|----------|-----------|
| **FFmpeg** | Video and audio conversion | Yes |
| **ImageMagick** | Image conversion, PDF to image | Yes |
| **Ghostscript** | PDF processing | Recommended |
| **LibreOffice** | Office documents (docx, xlsx, pptx) | Optional |

### Install commands by distro

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
| To Webm | WebM | VP9 codec |
| To Ogv | OGV | Theora codec |
| To Avi | AVI | MPEG-4/XviD |
| To Gif | GIF | 15fps, palette-optimized |
| To Gif (low quality) | GIF | 10fps, 75% scale |
| To Mp3 | MP3 | VBR ~190kbps |
| To Mp3 (low quality) | MP3 | VBR ~100kbps |
| To Aac | AAC | VBR ~155kbps |
| To Ogg | OGG | Vorbis ~160kbps |
| To Flac | FLAC | Lossless, max compression |
| To Wav | WAV | 16-bit PCM |
| To Png | PNG | Lossless |
| To Jpg | JPG | Quality 85 |
| To Webp | WebP | Quality 85 |
| To Avif | AVIF | Quality 80 |
| To Pdf | PDF | From images or documents |

All presets are customizable in the settings window or directly in `~/.config/fileconverter/settings.yaml`.

## Settings

```bash
fileconverter --settings
```

Or from the context menu: **File Converter > Configure presets...**

### What you can configure

**Global:** max simultaneous conversions, auto-close window, hardware acceleration (Off / Auto / NVENC / VAAPI), UI language.

**Per-preset:** output format, input file types, video quality/encoding speed/scale/rotation, audio bitrate/VBR/CBR/channels, image quality/scale/rotation, output filename template, post-conversion action, custom FFmpeg command override.

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

# Media Converter

![License](https://img.shields.io/badge/license-GPLv3-blue.svg)
![Platform](https://img.shields.io/badge/platform-Linux-green.svg)
![Nautilus](https://img.shields.io/badge/integration-Nautilus-orange.svg)

A media conversion tool that integrates directly into your Linux file manager. Convert audio and video files with just a few clicks, supporting multiple files and formats simultaneously.

⚠️**Please be aware**: This project is currently in its early stages. As such, you may encounter bugs or errors. I encourage you to use it with caution and at your own discretion. Thank you for your understanding!⚠️

## Features

- 🏠 Fully local
- 🎯 Direct integration with Nautilus file manager
- 📊 Real-time progress tracking

## Supported Formats

### Audio Formats
- MP3 (MPEG Layer-3 Audio)
- AAC (Advanced Audio Coding)
- WAV (Waveform Audio)
- FLAC (Free Lossless Audio Codec)
- OGG (Ogg Vorbis Audio)
- M4A (MPEG-4 Audio)
- OPUS (Opus Audio)
- WMA (Windows Media Audio)
- ALAC (Apple Lossless Audio Codec)
- AC3 (Dolby Digital Audio)
- AMR (Adaptive Multi-Rate Audio)
- AIFF (Audio Interchange File Format)

### Video Formats
- MP4 (MPEG-4 Video)
- MKV (Matroska Video)
- AVI (Audio Video Interleave)
- WebM (WebM Video)
- MOV (QuickTime Video)
- FLV (Flash Video)
- WMV (Windows Media Video)
- M4V (MPEG-4 Video)
- 3GP (3GPP Video)
- TS (MPEG Transport Stream)
- OGV (Ogg Video)
- VOB (DVD Video Object)

### Image Formats
- JPG (JPEG Image)
- PNG (Portable Network Graphics)
- WebP (WebP Image)
- GIF (Graphics Interchange Format)
- TIFF (Tagged Image File Format)
- BMP (Bitmap Image)
- HEIF (High Efficiency Image Format)
- ICO (Icon Image)

### Document Formats
- PDF (Portable Document Format)
- DOCX (Microsoft Word Document)
- ODT (OpenDocument Text)
- RTF (Rich Text Format)
- TXT (Plain Text)

### Subtitle Formats
- SRT (SubRip Subtitle)
- ASS (Advanced SubStation Alpha)

### Archive Formats
- ZIP (ZIP Archive)
- TAR (Tar Archive)
- TAR.GZ (Gzip Tar Archive)
- TAR.BZ2 (Bzip2 Tar Archive)

## Requirements

- Linux-based operating system
- Nautilus file manager
- FFmpeg and FFprobe (for audio, video, image, and subtitle processing)
- Zenity (for GUI dialogs)
- Unzip (for ZIP archive extraction)
- Tar (for TAR, TAR.GZ, and TAR.BZ2 archive extraction)
- LibreOffice and Unoconv (for document conversions)
- Ghostscript (for PDF processing)
- Optional: libheif (for HEIF image format support)

## Requirements
- Linux-based operating system
- Nautilus file manager
- FFmpeg and FFprobe (for audio, video, image, and subtitle processing)
- Zenity (for GUI dialogs)
- Unzip (for ZIP archive extraction)
- Tar (for TAR, TAR.GZ, and TAR.BZ2 archive extraction)
- LibreOffice and Unoconv (for document conversions)
- Ghostscript (for PDF processing)
- Optional: libheif (for HEIF image format support)

## Installation

1. Clone the repository:
```bash
git clone https://github.com/alexdevflow/media-converter.git
cd media-converter
```

2. Run the installation script:
```bash
chmod +x install.sh    # Make the installation script executable
./install.sh
```

3. Restart Nautilus:
```bash
nautilus -q
```

## Usage

1. Right-click on one file in Nautilus
2. Navigate to Scripts → Media Converter → [Audio/Video/...]
3. Select your desired output format
4. Monitor the conversion progress
5. Find the converted files in the same directory as the originals

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request. For major changes, please open an issue first to discuss what you would like to change.

1. Fork the Project
2. Create your Feature Branch (`git checkout -b feature/AmazingFeature`)
3. Commit your Changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the Branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## License

This project is licensed under the GPLv3 License - see the [LICENSE](LICENSE) file for details.

## Acknowledgments

- FFmpeg team for their amazing media processing framework 💝
- GNOME team for Nautilus file manager and the ease of adding such feature 💯
- All contributors who will help improve this tool 🤗

## Support

If you encounter any issues or have questions, please file an issue on the GitHub repository.

---
Made with ❤️ for the Linux community

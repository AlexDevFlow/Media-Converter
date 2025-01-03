# Media Converter

![License](https://img.shields.io/badge/license-GPLv3-blue.svg)
![Platform](https://img.shields.io/badge/platform-Linux-green.svg)
![Nautilus](https://img.shields.io/badge/integration-Nautilus-orange.svg)

A media conversion tool that integrates directly into your Linux file manager. Convert audio and video files with just a few clicks, supporting multiple files and formats simultaneously.

⚠️**Please be aware**: This project is currently in its early stages. As such, you may encounter bugs or errors. I encourage you to use it with caution and at your own discretion. Thank you for your understanding!⚠️

## Features

- 🏠 Fully local
- 🎯 Direct integration with Nautilus file manager
- 📊 Real-time progress tracking for each file
- 🎵 Wide range of audio formats supported
- 🎬 Comprehensive video format support
- 🚀 Parallel conversion processing

## Supported Formats

### Audio Formats
- MP3 (MPEG Layer-3 Audio)
- AAC (Advanced Audio Coding)
- WAV (Waveform Audio)
- FLAC (Free Lossless Audio Codec)
- OGG (Ogg Vorbis Audio)
- M4A (MPEG-4 Audio)
- WMA (Windows Media Audio)
- OPUS (Opus Audio)
- AC3 (Dolby Digital Audio)
- AMR (Adaptive Multi-Rate Audio)

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

## Requirements

- Linux-based operating system
- Nautilus file manager
- FFmpeg
- Zenity

## Installation

1. Clone the repository:
```bash
git clone https://github.com/alexdevflow/mediamorphosis.git
cd mediamorphosis
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

1. Right-click on one or more media files in Nautilus
2. Navigate to Scripts → Media Converter → [Audio/Video]
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

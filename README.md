# 🎵 Music Normalizer

A lightweight, multi-threaded desktop application for batch normalizing audio and video files using loudness analysis (LUFS-based normalization with FFmpeg).

## Features

✨ **Multi-threaded Processing** - Uses all CPU cores for parallel processing
🎯 **LUFS-based Normalization** - Two-pass loudness normalization to prevent clipping
🎬 **Video Support** - Automatically extracts and normalizes audio from videos
📁 **Batch Processing** - Process entire folders of audio/video files
🔧 **Smart FFmpeg Detection** - Finds FFmpeg automatically from bundle, local directory, or system PATH
💾 **Safe Output** - Saves normalized files to a separate `normalized/` folder

## Supported Formats

**Audio:** MP3, FLAC, WAV, M4A, OGG, OPUS, AAC, WMA
**Video:** MP4, MKV, AVI, MOV, WMV, FLV, WEBM (converts to M4A audio)

## Installation & Usage

### Option 1: Download Pre-built Executable (Recommended)

1. Go to [Releases](https://github.com/giuseppegg02/music-normalizer/releases)
2. Download the latest `normalize_music.exe`
3. Place it in your music folder
4. Run it and follow the GUI

### Option 2: Run from Source

**Requirements:**
- Python 3.13+
- FFmpeg installed on your system

**Setup:**
```bash
# Clone the repository
git clone https://github.com/giuseppegg02/music-normalizer.git
cd music-normalizer

# Create virtual environment
python -m venv venv
.\venv\Scripts\activate

# Install dependencies
pip install pyinstaller

# Run the app
python normalize_music.py
```

### Building from Source

```bash
# Ensure PyInstaller is installed
pip install pyinstaller

# Build the executable
python -m PyInstaller normalize_music.spec --clean -y

# The executable will be in dist/normalize_music.exe
```

## How It Works

1. **Select Target Loudness**
   - Conservativo (-16 LUFS) - Safe, no clipping risk
   - Standard Streaming (-14 LUFS) - YouTube, Spotify standard
   - Più Forte (-12 LUFS) - Louder output

2. **Click "Avvia Normalizzazione"**
   - App scans the folder for audio/video files
   - Processes files in parallel using all available CPU cores
   - Uses two-pass loudness normalization to prevent artifacts

3. **Results**
   - Normalized files saved to `normalized/` folder
   - Original files remain untouched
   - Detailed log shows processing status for each file

## Technical Details

### Multi-threading Architecture
- Main thread: GUI updates via `threading.Thread` and `queue.Queue`
- Worker threads: File processing via `concurrent.futures.ThreadPoolExecutor`
- Thread-safe: Uses `threading.Lock` for shared state

### Loudness Normalization
Two-pass loudness normalization (see [TRIMMING_FIX.md](TRIMMING_FIX.md)):
1. **Pass 1**: Analyze loudness and measure parameters
2. **Pass 2**: Apply normalization with measured parameters to prevent clipping

### Build System
- **PyInstaller** for executable creation
- **GitHub Actions** for automated CI/CD and releases
- **FFmpeg embedding** for standalone distribution

## Troubleshooting

### "ffmpeg not found" error
- Download FFmpeg from https://ffmpeg.org/download.html
- Extract `ffmpeg.exe` and place it in the same folder as the app
- Or install via: `choco install ffmpeg` (requires Chocolatey)

### Build errors
- Check `build/normalize_music/warn-normalize_music.txt` for warnings
- Ensure FFmpeg binary is in the same directory as the script during build

## Project Structure

```
.
├── normalize_music.py       # Main application (GUI + logic)
├── normalize_music.spec     # PyInstaller configuration
├── version_info.txt         # Windows version info
├── TRIMMING_FIX.md         # Technical details on two-pass normalization
├── logo.ico                 # Application icon
└── .github/
    └── workflows/
        └── build-and-release.yml  # CI/CD pipeline
```

## Development

### Running Tests
```bash
# Run the GUI
python normalize_music.py
```

### Packaging
```bash
# Build new release
python -m PyInstaller normalize_music.spec --clean -y

# Check dist/normalize_music.exe
```

## License

This project is open-source. Feel free to modify and distribute.

## Contributing

Contributions welcome! Please:
1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push to the branch
5. Open a Pull Request

---

**Made with ❤️ for audio normalization enthusiasts**

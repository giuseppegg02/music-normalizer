# Copilot / AI agent instructions for Music Normalizer

This repo is a small, single-window Tkinter GUI app that batch-normalizes audio/video files using FFmpeg.
Keep instructions concise and actionable for quick edits, builds and packaging.

- Purpose: `normalize_music.py` is a multi-threaded audio/video loudness normalizer (GUI + worker threads). See [normalize_music.py](normalize_music.py).
- Run locally: start the GUI during development with:

```bash
python normalize_music.py
```

- Packaging: the project uses PyInstaller with `normalize_music.spec` to build a single executable. The spec explicitly includes `ffmpeg.exe` in `binaries=[('ffmpeg.exe', '.')]`. Build with:

```bash
python -m PyInstaller normalize_music.spec --clean -y
```

- FFmpeg handling: the app looks for `ffmpeg.exe` in three places (in order): embedded inside the PyInstaller bundle, in the same directory as the script/exe, or in the system `PATH`. When packaging, include `ffmpeg.exe` via the spec (already done). If the build fails, inspect `build/warn-normalize_music.txt` and the `build/` folder for clues.

- Audio processing model and important behavior:

  - Two-pass `loudnorm` (FFmpeg) is implemented to avoid trimming; see [TRIMMING_FIX.md](TRIMMING_FIX.md) for the rationale and the exact FFmpeg commands used.
  - Video inputs are converted to `m4a` audio output (see `video_formats` and the conversion branch in `normalize_file`).
  - Output folder: normalized files are written to `normalized/` next to the script/exe.

- Concurrency & UI patterns to preserve:

  - Heavy work runs on threads via `concurrent.futures.ThreadPoolExecutor` (worker count uses `os.cpu_count()`). See `process_files()` in [normalize_music.py](normalize_music.py).
  - UI thread receives logs via `queue.Queue()` and `self.root.after()` polling. Use `self.log_queue.put(('__progress__', value))` to update progress.
  - Keep FFmpeg calls and any blocking subprocess runs off the UI thread.

- Common failure modes and quick fixes:

  - ffmpeg not found → UI disables start button and shows the instructions to place `ffmpeg.exe` next to the exe or install via package manager (choco). Check `get_ffmpeg_path()` and `check_ffmpeg()`.
  - Two-pass JSON parsing can fail; the code falls back to single-pass mode (see parsing logic in `normalize_file`). If you change parsing, keep a safe fallback.
  - Long-running conversions may hit timeouts (timeouts in subprocess.run are present). Increase timeout only when necessary and keep UI responsive.

- Code hotspots and where to edit for common tasks:

  - Change supported input formats: modify `supported_formats` and `video_formats` in `MusicNormalizer.__init__`.
  - Adjust target LUFS presets: `get_target_lufs()` in `NormalizerGUI` maps combobox options to numeric LUFS.
  - Modify encoding/settings for audio outputs in `normalize_file()` (the branch for `is_video` uses AAC/192k, audio uses implicit codec).

- Packaging/version points:

  - App version and Windows version resource are defined in [version_info.txt](version_info.txt) and referenced by the spec's `version` parameter.
  - The spec sets `console=False` and `icon='logo.ico'` — keep GUI packaging settings when editing the exe behavior.

- Dev workflow notes for PRs:
  - Run the app locally before packaging to validate behavior (`python normalize_music.py`).
  - For packaging changes, run PyInstaller and inspect `build/` and `dist/` outputs. If `ffmpeg.exe` is missing in the bundle, add it to `binaries` in the spec.

If anything above is unclear or you want extra examples (e.g., expanding the sample FFmpeg two-pass flow, or adding a small CLI test harness), tell me which section to expand.
